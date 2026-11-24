"""模型调用：DeepSeek（OpenAI 兼容协议）+ 联调用的假数据流。

本服务无状态，不读写数据库；会话与消息全部由 Java 侧维护。
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import settings
from app.prompts import meta

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

FAKE_REPLY = (
    "（联调模式）我已经收到你的问题。这里返回的是模拟数据，"
    "用于验证 Java 到 FastAPI 的流式链路是否正常。"
)

# 懒加载客户端
def _client_instance() -> AsyncOpenAI:
    """懒加载客户端，避免联调模式下强制要求 API Key。"""
    global _client
    if _client is None:
        if not settings.deepseek_api_key:
            raise RuntimeError("AI_PROVIDER=deepseek 时必须配置 AI_DEEPSEEK_API_KEY")
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.request_timeout,
        )
    return _client

# 裁剪消息，最近聊天中只保留若干条
def _trim(messages: list[dict]) -> list[dict]:
    """只保留最近若干条消息，system 提示始终保留，避免超出上下文窗口。"""
    if len(messages) <= settings.max_history:
        return messages
    system = [m for m in messages if m["role"] == "system"][:1]
    return system + messages[-settings.max_history:]

# 按场景注入系统提示词
# 上游已带 system 时让位，保留 Java 侧紧急覆盖能力
def _prepare(messages: list[dict], scene: str | None) -> list[dict]:
    """返回可发给模型的消息：缺 system 时按 scene 补上，然后再裁剪历史。"""
    if any(m.get("role") == "system" for m in messages):
        logger.debug("上游已带 system，跳过注入 scene=%s", scene)
        return _trim(messages)

    text, label = meta(scene)
    logger.debug("注入系统提示词 scene=%s prompt=%s", scene, label)
    return _trim([{"role": "system", "content": text}, *messages])

# 聊天流式输出
async def stream_chat(messages: list[dict], scene: str | None = None) -> AsyncIterator[str]:
    """逐段产出模型输出的文本增量。"""
    messages = _prepare(messages, scene)

    if settings.provider == "fake":
        for ch in FAKE_REPLY:
            await asyncio.sleep(0.01)
            yield ch
        return

    # 创建流式请求
    stream = await _client_instance().chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,  # type: ignore[arg-type]
        stream=True,
        temperature=0.7,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        text = chunk.choices[0].delta.content
        if text:
            yield text

# 聊天同步输出
async def complete_chat(messages: list[dict], scene: str | None = None) -> str:
    """一次性返回完整文本，用于报告类同步接口。"""
    messages = _prepare(messages, scene)

    if settings.provider == "fake":
        return "（联调模式）这是一份模拟的报告内容，用于验证同步接口链路。"

    resp = await _client_instance().chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.3,
        stream=False,
    )
    return resp.choices[0].message.content or ""