from dataclasses import dataclass, field
from typing import Any

from .session import ModelSelection

Message = dict[str, Any]


@dataclass(frozen=True)
class IncomingMessage:
    """统一入站消息；渠道生成会话键，基类补入该会话已保存的模型选择。"""

    channel: str
    user_id: str
    session_id: str
    text: str
    message_id: str = ""
    model: ModelSelection | None = None


@dataclass(frozen=True)
class Reply:
    """业务处理结果：发送的文本，以及需要保存的完整对话轮次。

    messages 为空时只发送文本，不加入模型历史，例如一次失败提示。
    model 非空时同时更新会话选择；不包含任何供应商客户端或凭据。
    """

    text: str
    messages: list[Message] = field(default_factory=list)
    model: ModelSelection | None = None
