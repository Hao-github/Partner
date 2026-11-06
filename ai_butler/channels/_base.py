from abc import ABC, abstractmethod
from collections.abc import Callable
from threading import Event

from ..config import Config, config
from ..models import IncomingMessage, Message, Reply

MessageHandler = Callable[[IncomingMessage, list[Message]], Reply]
IncomingHandler = Callable[[IncomingMessage], None]


class Channel(ABC):
    """平台收发契约、停止状态与清理钩子，不处理历史或持久化。"""

    def __init__(self, settings: Config = config):
        """保存只读启动配置并创建平台共用的停止信号。"""
        self._settings = settings
        self._stopping = Event()

    @classmethod
    def inspect(cls, *, discover: bool = False, settings: Config = config) -> None:
        """平台按需实现诊断；不实例化渠道或模型。"""
        raise ValueError(f"{cls.__name__} 不支持渠道诊断或发送者识别。")

    def receive(self, handler: IncomingHandler) -> None:
        """阻塞接收统一消息，将消息交给服务提供的回调。"""
        if not self._stopping.is_set():
            self._receive(handler)

    def reply(self, incoming: IncomingMessage, text: str) -> bool:
        """平台实现处理路由与发送；返回发送完成且未关闭的状态。"""
        if self._stopping.is_set():
            return False
        self._send(incoming, text)
        return not self._stopping.is_set()

    def close(self) -> None:
        """停止接收并释放资源，可重复调用。"""
        self._stopping.set()
        self._close()

    def failure_reply(self, error: RuntimeError) -> str:
        """默认让调用方呈现错误；平台可改为向用户回复统一提示。"""
        raise error

    @abstractmethod
    def _receive(self, handler: IncomingHandler) -> None:
        """接收平台消息，交给服务回调。"""

    @abstractmethod
    def _send(self, incoming: IncomingMessage, text: str) -> None:
        """发送文本；具体协议、原消息关联和限速留在子类。"""

    def _close(self) -> None:
        """子类有连接或工作线程时，在此释放。"""
        return
