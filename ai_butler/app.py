import logging

from .channels import create_channel
from .config import Config, config
from .core.agent import Agent
from .models import IncomingMessage, Message, ModelSelection, Reply
from .providers import create_provider

logger = logging.getLogger(__name__)
_MODEL_HELP = (
    "用法：/model 查看模型；/model 模型名；/model 供应商 模型名；/model default 恢复启动默认模型。"
)


class Butler:
    """应用入口：选择渠道与模型，组装两个端口，不参与底层协议。

    Channel 负责会话与交付，Agent 负责模型与工具；应用组装并按会话路由模型。
    run 阻塞运行并在退出时关闭渠道。
    """

    def __init__(
        self,
        channel: str = "cli",
        *,
        provider: str | None = None,
        model: str | None = None,
        session: str = "default",
        settings: Config = config,
    ):
        self._settings = settings.select_model(provider=provider, model=model)
        self._default_model = ModelSelection(self._settings.provider, self._settings.model)
        self._agents: dict[ModelSelection, Agent] = {}
        self._agent(self._default_model)
        self._channel = create_channel(channel, session=session, settings=self._settings)
        self._channel_name = channel

    def run(self) -> None:
        """接收统一消息，交给 Agent，再由渠道发送返回的回答。"""
        logger.info(
            "app_started channel=%s provider=%s model=%s",
            self._channel_name,
            self._settings.provider,
            self._settings.model,
        )
        try:
            self._channel.receive(self._respond)
        finally:
            self.close()

    def _agent(self, selection: ModelSelection) -> Agent:
        """按模型复用无会话状态的 Agent，配置验证成功后才加入缓存。"""
        if selection not in self._agents:
            settings = self._settings.select_model(
                provider=selection.provider, model=selection.model
            )
            self._agents[selection] = Agent(create_provider(settings), settings)
        return self._agents[selection]

    def _respond(self, incoming: IncomingMessage, history: list[Message]) -> Reply:
        selection = incoming.model or self._default_model
        parts = incoming.text.split()
        if parts and parts[0] == "/model":
            return self._model_command(parts[1:], selection)
        try:
            agent = self._agent(selection)
        except ValueError as error:
            return Reply(f"模型配置不可用：{error} 可用 /model default 恢复默认模型。")
        return agent.reply(incoming, history)

    def _model_command(self, args: list[str], current: ModelSelection) -> Reply:
        """模型命令不调用模型、不加入历史；选择由渠道与回复一起提交。"""
        if not args:
            return Reply(f"当前模型：{current.provider} / {current.model}\n{_MODEL_HELP}")
        if args == ["default"]:
            selected = self._default_model
        elif len(args) == 1:
            selected = ModelSelection(current.provider, args[0])
        elif len(args) == 2:
            selected = ModelSelection(args[0].lower(), args[1])
        else:
            return Reply(_MODEL_HELP)
        try:
            self._agent(selected)
        except ValueError as error:
            return Reply(f"模型切换失败：{error}")
        logger.info("model_selected provider=%s model=%s", selected.provider, selected.model)
        return Reply(f"已切换模型：{selected.provider} / {selected.model}", model=selected)

    def close(self) -> None:
        """停止接收并释放渠道资源；可重复调用。"""
        self._channel.close()
        logger.info("app_stopped channel=%s", self._channel_name)
