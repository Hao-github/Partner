"""Agent 内部的模型工厂，不作为应用调用接口。"""

from ..config import Config, config
from ._base import Provider as _Provider
from ._deepseek import DeepSeekProvider as _DeepSeekProvider
from ._openai import OpenAIProvider as _OpenAIProvider

__all__: list[str] = []


def _create_provider(settings: Config = config) -> _Provider:
    """统一创建入口；供应商差异封装在各自的实现中。"""
    settings.validate()
    if settings.provider == "deepseek":
        return _DeepSeekProvider(settings)
    return _OpenAIProvider(settings)
