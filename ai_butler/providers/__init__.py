"""模型服务适配。只负责模型协议，不处理 QQ 等渠道。"""

from ..config import Config, config
from .base import Provider
from .chat_completions import DeepSeekProvider, OpenAIProvider

__all__ = ["Provider", "create_provider"]


def create_provider(settings: Config = config) -> Provider:
    """统一创建入口；供应商差异封装在各自的实现中。"""
    settings.validate()
    if settings.provider == "deepseek":
        return DeepSeekProvider(settings)
    return OpenAIProvider(settings)
