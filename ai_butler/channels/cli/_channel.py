import re
from collections.abc import Callable

from ...config import Config, config
from ...models import IncomingMessage, Message
from .._base import Channel, IncomingHandler

_HELP = (
    "命令：/help 帮助；/session 名称 切换会话；/history 查看最近记录；"
    "/model 查看或切换模型；/version 查看版本；/exit 退出。"
)
_SESSION_PATTERN = re.compile(r"[\w.-]{1,64}\Z")


def _session_name(value: str) -> str:
    """在终端输入边界校验会话名，拒绝空值和非法字符。"""
    if not _SESSION_PATTERN.fullmatch(value):
        raise ValueError("会话名限 1–64 个中文、字母、数字、下划线、点或短横线。")
    return value


class CLIChannel(Channel):
    """终端渠道：内部处理命令与会话切换，只把聊天消息交给业务回调。"""

    def __init__(
        self,
        session: str = "default",
        settings: Config = config,
        *,
        history: Callable[[str], list[Message]],
    ):
        """校验初始会话并保存只读历史回调，不直接访问存储。"""
        super().__init__(settings)
        self._session = _session_name(session)
        self._history = history

    def _receive(self, handler: IncomingHandler) -> None:
        """读取输入并处理终端命令，其余消息交给业务回调。"""
        print(f"AI 管家 | 会话：{self._session}")
        print(_HELP)
        while not self._stopping.is_set():
            try:
                text = input(f"你 [{self._session}]> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。完整对话已保存。")
                return
            if text in {"/exit", "/quit", "exit", "quit"}:
                print("已退出。完整对话已保存。")
                return
            try:
                if not text or self._command(text):
                    continue
                print("管家正在思考…", flush=True)
                incoming = IncomingMessage(
                    channel="cli", user_id="local", session_id=f"live:{self._session}", text=text
                )
                handler(incoming)
            except RuntimeError as error:
                print(f"提示：{error}")
            except KeyboardInterrupt:
                print("\n已取消当前回复，此轮未保存。可以继续输入或 /exit。")

    def _command(self, text: str) -> bool:
        """执行帮助、切会话和历史命令，返回是否已消费输入。"""
        if text == "/help":
            print(_HELP)
        elif text == "/session" or text.startswith("/session "):
            try:
                self._session = _session_name(text.partition(" ")[2].strip())
                print(f"已切换会话：{self._session}")
            except ValueError as error:
                print(error)
        elif text == "/history":
            self._show_history()
        else:
            return False
        return True

    def _show_history(self) -> None:
        """通过回调读取当前会话，只显示用户和助手的非空文本。"""
        history = self._history(f"live:{self._session}")
        if not history:
            print("当前会话暂无记录。")
        for message in history:
            if message["role"] in {"user", "assistant"} and message.get("content"):
                label = "你" if message["role"] == "user" else "管家"
                print(f"{label}: {message['content']}")

    def _send(self, incoming: IncomingMessage, text: str) -> None:
        """在终端显示回复，不暴露输出格式给业务层。"""
        print(f"管家> {text}")
