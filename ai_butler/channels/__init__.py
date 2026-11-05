"""渠道公共入口；调用方只接触统一消息和收发接口。"""

from ..config import Config, config
from .base import Channel, MessageHandler
from .cli import CLIChannel as _CLIChannel
from .qq import QQChannel as _QQChannel

__all__ = ["Channel", "MessageHandler", "create_channel", "inspect_channel"]


def create_channel(name: str, *, session: str = "default", settings: Config = config) -> Channel:
    if name == "cli":
        return _CLIChannel(session, settings)
    if name == "qq":
        return _QQChannel(settings)
    raise ValueError(f"不支持的渠道：{name}")


def inspect_channel(name: str, *, discover: bool = False, settings: Config = config) -> None:
    """检查渠道连接或识别发送者，不调用模型。"""
    if name != "qq":
        raise ValueError("只有 QQ 渠道支持连接检查和发送者识别。")
    _QQChannel.inspect(discover=discover, settings=settings)
