"""内部接口：只允许 Java 侧通过 X-Internal-Token 调用。

注意：本服务不鉴权用户身份，用户令牌不会传到这里；
userId 由 Java 侧从 JWT 解析后传入。
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.prompts import meta
from app.schemas.chat import ChatStreamRequest, ReportRequest
from app.services.llm import complete_chat, stream_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify(token: str | None) -> None:
    if token != settings.internal_token:
        logger.warning("内部令牌校验失败")
        raise HTTPException(status_code=401, detail="invalid internal token")


def _sse(event: str, data: dict) -> str:
    """SSE 帧：一行 event、一行 data、一个空行结束。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

# 聊天流
@router.post("/chat/stream")
async def chat_stream(
    req: ChatStreamRequest,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> StreamingResponse:
    _verify(x_internal_token)
    # Java 侧漏传时兜底生成，保证三处日志与响应头用的是同一个值
    trace_id = x_trace_id or uuid.uuid4().hex
    # 上游自带 system 时以它为准，否则按 scene 注入（与 llm._prepare 的判定保持一致）
    prompt_label = "upstream" if any(m.role == "system" for m in req.messages) else meta(req.scene)[1]
    logger.info(
        "stream start user=%s conversation=%s scene=%s trace=%s prompt=%s",
        req.userId, req.conversationId, req.scene, trace_id, prompt_label,
    )

    # 生成器
    async def gen():
        try:
            async for delta in stream_chat([m.model_dump() for m in req.messages], req.scene):
                yield _sse("delta", {"text": delta})
            yield _sse("done", {})
        except asyncio.CancelledError:
            # Java 侧断开连接，属正常场景，直接结束
            logger.info("stream cancelled user=%s trace=%s", req.userId, trace_id)
            raise
        except Exception:
            # 流已开始，无法再改 HTTP 状态码，只能通过事件告知
            logger.exception(
                "stream failed user=%s conversation=%s trace=%s",
                req.userId, req.conversationId, trace_id,
            )
            # 带上 traceId，方便用户报障时直接定位
            yield _sse("error", {"message": "AI 服务异常", "traceId": trace_id})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx 默认会缓冲响应，必须显式关闭，否则 SSE 变成一次性返回
            "X-Accel-Buffering": "no",
            # 流开始前就发出，Java 侧可据此与自己的日志对齐
            "X-Trace-Id": trace_id,
        },
    )

# 报表生成
@router.post("/report")
async def report(
    req: ReportRequest,
    response: Response,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> dict:
    _verify(x_internal_token)
    # 同步接口没有 SSE 帧，trace 只能靠响应头与日志带出
    trace_id = x_trace_id or uuid.uuid4().hex
    response.headers["X-Trace-Id"] = trace_id
    prompt_label = meta(req.scene)[1]
    logger.info(
        "report start user=%s scene=%s trace=%s prompt=%s",
        req.userId, req.scene, trace_id, prompt_label,
    )
    try:
        content = await complete_chat(
            [{"role": "user", "content": json.dumps(req.payload, ensure_ascii=False)}],
            req.scene,
        )
    except Exception:
        logger.exception("report failed user=%s scene=%s trace=%s", req.userId, req.scene, trace_id)
        raise
    logger.info("report done user=%s scene=%s trace=%s chars=%d", req.userId, req.scene, trace_id, len(content))
    return {"content": content}