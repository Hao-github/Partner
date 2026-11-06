from dataclasses import replace
from typing import Any

from ..config import Config, config
from ..models import Message, ModelSelection
from ._base import Provider
from ._deepseek import DeepSeekProvider as _DeepSeekProvider
from ._openai import OpenAIProvider as _OpenAIProvider


class ModelService:
    """对外提供模型配置和统一消息，内部选择并复用 Provider。"""

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        settings: Config = config,
    ):
        default = self._create_provider(settings.select_model(provider=provider, model=model))
        self.settings = default.config
        self.default_model = ModelSelection(self.settings.provider, self.settings.model)
        self._providers = {self.default_model: default}

    @staticmethod
    def _provider_type(name: str) -> type[Provider]:
        match name:
            case "deepseek":
                return _DeepSeekProvider
            case "openai":
                return _OpenAIProvider
        raise ValueError(f"不支持的 BUTLER_PROVIDER：{name}。")

    @staticmethod
    def _create_provider(settings: Config) -> Provider:
        provider_type = ModelService._provider_type(settings.provider)
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

    def resolve(self, selection: ModelSelection, *, validate: bool = True) -> Config:
        """准备会话配置与客户端；版本查询可仅查看配置，不要求凭据可用。"""
        if provider := self._providers.get(selection):
            return provider.config
        settings = self.settings.select_model(provider=selection.provider, model=selection.model)
        if not validate:
            return settings
        provider = self._create_provider(settings)
        self._providers[selection] = provider
        return provider.config

    def complete(
        self, selection: ModelSelection, messages: list[Message], tools: list[dict[str, Any]]
    ) -> Message:
        self.resolve(selection)
        return self._providers[selection].complete(messages, tools)
