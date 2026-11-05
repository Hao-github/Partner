import re

from ...config import Config, config
from ...models import IncomingMessage
from .._base import Channel, MessageHandler

_HELP = (
    "命令：/help 帮助；/session 名称 切换会话；/history 查看最近记录；"
    "/model 查看模型，/model [供应商] 模型名 切换模型；/exit 退出。"
)
_SESSION_PATTERN = re.compile(r"[\w.-]{1,64}\Z")


def _session_name(value: str) -> str:
    if not _SESSION_PATTERN.fullmatch(value):
        raise ValueError("会话名限 1–64 个中文、字母、数字、下划线、点或短横线。")
    return value


class CLIChannel(Channel):
    """终端渠道：内部处理命令与会话切换，只把聊天消息交给业务回调。"""

    def __init__(self, session: str = "default", settings: Config = config):
        super().__init__(settings)
        self._session = _session_name(session)

    def _receive(self, handler: MessageHandler) -> None:
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
                self._process(incoming, handler)
            except RuntimeError as error:
                print(f"提示：{error}")
            except KeyboardInterrupt:
                print("\n已取消当前回复，此轮未保存。可以继续输入或 /exit。")

    def _command(self, text: str) -> bool:
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
        elif text.split(maxsplit=1)[0] == "/model":
            return False
        elif text.startswith("/"):
            print(f"未知命令。{_HELP}")
        else:
            return False
        return True

    def _show_history(self) -> None:
        history = self.history(f"live:{self._session}")
        if not history:
            print("当前会话暂无记录。")
        for message in history:
            if message["role"] in {"user", "assistant"} and message.get("content"):
                label = "你" if message["role"] == "user" else "管家"
                print(f"{label}: {message['content']}")

    def _send(self, incoming: IncomingMessage, text: str) -> None:
        """在终端显示回复，不暴露输出格式给业务层。"""
        print(f"管家> {text}")
