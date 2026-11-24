"""内部接口的请求模型。

字段命名与 Java 侧 DTO 保持一致（camelCase），避免 Java 侧再做字段映射。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# 单条对话消息
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


# 对话流请求
class ChatStreamRequest(BaseModel):
    """Java 转发流式对话时提交的数据。"""

    userId: int
    conversationId: str
    scene: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)


# 报表请求
class ReportRequest(BaseModel):
    """同步长请求（匹配报告、简历解析等）。"""

    userId: int
    scene: str
    payload: dict[str, Any] = Field(default_factory=dict)