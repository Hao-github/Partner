"""Agent 内部的渠道工厂，不作为应用调用接口。"""

from ..config import Config, config
from ._base import Channel as _Channel
from .cli._channel import CLIChannel as _CLIChannel
from .qq._channel import QQChannel as _QQChannel

__all__: list[str] = []


def _create_channel(name: str, *, session: str = "default", settings: Config = config) -> _Channel:
    if name == "cli":
        return _CLIChannel(session, settings)
    if name == "qq":
        return _QQChannel(settings)
    raise ValueError(f"不支持的渠道：{name}")


def _inspect_channel(name: str, *, discover: bool = False, settings: Config = config) -> None:
    """检查渠道连接或识别发送者，不调用模型。"""
    if name != "qq":
        raise ValueError("只有 QQ 渠道支持连接检查和发送者识别。")
    _QQChannel.inspect(discover=discover, settings=settings)
