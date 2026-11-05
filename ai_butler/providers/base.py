from abc import ABC, abstractmethod
from typing import Any

from ..models import Message


class Provider(ABC):
    """模型端口：接受会话与工具描述，返回统一的文本或工具调用消息。

    HTTP、鉴权、供应商参数和重试均由实现负责；失败抛出已脱敏的 RuntimeError。
    """

    @abstractmethod
    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        """生成一条统一模型消息；调用方不需要了解供应商协议。"""
