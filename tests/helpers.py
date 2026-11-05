import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ai_butler import Agent
from ai_butler.channels._base import Channel, MessageHandler
from ai_butler.config import Config
from ai_butler.models import IncomingMessage
from ai_butler.storage.sessions import SessionStore


def completion(text: str | None = "你好", *, calls=None, finish="stop"):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = calls
    return {"choices": [{"message": message, "finish_reason": finish}]}


def tool_call(call_id="call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "get_beijing_time", "arguments": "{}"},
    }


def tool_message(*call_ids: str):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call(call_id) for call_id in call_ids],
    }


class ProjectTest(unittest.TestCase):
    def setUp(self):
        guard = patch("socket.socket.connect", side_effect=AssertionError("测试禁止网络连接"))
        guard.start()
        self.addCleanup(guard.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch.dict(os.environ, {}, clear=True):
            self.settings = Config(
                deepseek_api_key="test-secret", db_path=self.root / "sessions.sqlite3"
            )

    def store(self):
        store = SessionStore(self.settings.db_path)
        self.addCleanup(store.close)
        return store

    def create_agent(self, provider, **changes):
        with patch("ai_butler.core.agent._create_provider", return_value=provider):
            agent = Agent(settings=replace(self.settings, **changes))
        self.addCleanup(agent.close)
        return agent


class RecordingChannel(Channel):
    """只替换平台收发，实际运行基类的会话与交付流程。"""

    def __init__(self, settings: Config):
        super().__init__(settings)
        self.messages: list[IncomingMessage] = []
        self.sent: list[str] = []

    def _receive(self, handler: MessageHandler) -> None:
        for message in self.messages:
            self._process(message, handler)

    def _send(self, incoming: IncomingMessage, text: str) -> None:
        self.sent.append(text)
