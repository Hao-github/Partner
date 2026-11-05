"""Agent 内部的模型工厂，不作为应用调用接口。"""

from dataclasses import replace

from ..config import Config, config
from ._base import Provider as _Provider
from ._deepseek import DeepSeekProvider as _DeepSeekProvider
from ._openai import OpenAIProvider as _OpenAIProvider

__all__: list[str] = []


def _provider_type(name: str) -> type[_Provider]:
    match name:
        case "deepseek":
            return _DeepSeekProvider
        case "openai":
            return _OpenAIProvider
    raise ValueError(f"不支持的 BUTLER_PROVIDER：{name}。")


def _create_provider(settings: Config = config) -> _Provider:
    """选择实现并应用其默认配置；Agent 不需要了解供应商。"""
    provider_type = _provider_type(settings.provider)
    prefix = settings.provider.upper()
    settings = replace(
        settings,
        model=settings.model
        or settings.options.get(f"{prefix}_MODEL", provider_type.default_model),
        base_url=settings.base_url
        or settings.options.get(f"{prefix}_BASE_URL", provider_type.default_base_url),
    )
    settings.validate()
    return provider_type(settings)
