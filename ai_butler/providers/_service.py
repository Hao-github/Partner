from typing import Any

from ..config import Config, config
from ..models import Message, ModelSelection
from ._base import Provider
from ._deepseek import DeepSeekProvider as _DeepSeekProvider
from ._openai import OpenAIProvider as _OpenAIProvider


class ModelService:
    """对外提供模型选择和统一消息，配置与客户端只在服务内部维护。"""

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        settings: Config = config,
    ):
        """基于冻结的启动快照创建默认模型，并建立服务独立的客户端缓存。"""
        self._settings = settings
        default = self._create_provider(settings, provider=provider, model=model)
        self.default_model = ModelSelection(default.config.provider, default.config.model)
        self._providers = {self.default_model: default}

    @staticmethod
    def _provider_type(name: str) -> type[Provider]:
        """唯一的供应商类型选择入口；新增实现只扩展此分支。"""
        match name:
            case "deepseek":
                return _DeepSeekProvider
            case "openai":
                return _OpenAIProvider
        raise ValueError(f"不支持的 BUTLER_PROVIDER：{name}。")

    @staticmethod
    def _create_provider(
        settings: Config, *, provider: str | None = None, model: str | None = None
    ) -> Provider:
        """选择类型并构造客户端；完整模型配置由 Provider 初始化。"""
        name = settings.provider if provider is None else provider.strip().lower()
        return ModelService._provider_type(name)(settings, model=model)

    def prepare(self, selection: ModelSelection) -> None:
        """验证会话模型并缓存客户端；失败不入缓存，也不向外返回配置。"""
        if selection in self._providers:
            return
        self._providers[selection] = self._create_provider(
            self._settings, provider=selection.provider, model=selection.model
        )

    def complete(
        self, selection: ModelSelection, messages: list[Message], tools: list[dict[str, Any]]
    ) -> Message:
        """复用所选客户端生成统一消息，不改动启动配置。"""
        self.prepare(selection)
        return self._providers[selection].complete(messages, tools)
