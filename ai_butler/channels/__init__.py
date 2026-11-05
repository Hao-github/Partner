"""Agent 内部的渠道工厂，不作为应用调用接口。"""

from ..config import Config, config
from ._base import Channel as _Channel
from .cli._channel import CLIChannel as _CLIChannel
from .qq._channel import QQChannel as _QQChannel

__all__: list[str] = []


def _channel_type(name: str) -> type[_Channel]:
    match name:
        case "cli":
            return _CLIChannel
        case "qq":
            return _QQChannel
    raise ValueError(f"不支持的渠道：{name}")


def _create_channel(name: str, *, session: str = "default", settings: Config = config) -> _Channel:
    if name == "cli":
        return _CLIChannel(session, settings)
    return _channel_type(name)(settings)
