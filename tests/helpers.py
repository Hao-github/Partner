import os
import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ai_butler import Agent
from ai_butler.channels._base import Channel, IncomingHandler
from ai_butler.config import Config
from ai_butler.models import IncomingMessage, Message
from ai_butler.providers._base import Provider
from ai_butler.providers._deepseek import DeepSeekProvider
from ai_butler.storage.sessions import SessionStore

VERSION_TOOL = {
    "type": "function",
    "function": {
        "name": "get_version",
        "description": "Provider 透传工具描述的测试样例。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}


def completion(text: str | None = "你好", *, calls=None, finish="stop"):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = calls
    return {"choices": [{"message": message, "finish_reason": finish}]}


def tool_call(call_id="call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "get_version", "arguments": "{}"},
    }


def tool_message(*call_ids: str):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call(call_id) for call_id in call_ids],
    }


class ExtraProvider(Provider):
    """只在测试中使用的第三种协议适配，验证主流程不依赖供应商名称。"""

    name = "extra"
    default_model = "extra-default"
    default_base_url = "https://extra.invalid"

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        return {"role": "assistant", "content": f"{self.config.model}: {messages[-1]['content']}"}

    @staticmethod
    def _status_message(status: int) -> str:
        return f"Extra HTTP {status}"


class ProjectTest(unittest.TestCase):
    def setUp(self):
        original_connect = socket.socket.connect

        def connect(sock, address):
            # Windows asyncio 通过 loopback socketpair 唤醒事件循环。
            if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
                return original_connect(sock, address)
            raise AssertionError("测试禁止外部网络连接")

        guard = patch("socket.socket.connect", new=connect)
        guard.start()
        self.addCleanup(guard.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch.dict(os.environ, {}, clear=True):
            self.settings = Config(
                model="deepseek-flash",
                base_url="https://api.deepseek.com",
                options={"DEEPSEEK_API_KEY": "test-secret"},
                db_path=self.root / "sessions.sqlite3",
            )

    def store(self):
        store = SessionStore(self.settings.db_path)
        self.addCleanup(store.close)
        return store

    def create_agent(self, provider, **changes):
        settings = replace(self.settings, **changes)
        patcher = patch.object(DeepSeekProvider, "complete", provider.complete)
        patcher.start()
        self.addCleanup(patcher.stop)
        agent = Agent(settings=settings)
        self.addCleanup(agent.close)
        return agent


class RecordingChannel(Channel):
    """只替换平台收发，由服务负责实际会话与交付流程。"""

    def __init__(self, settings: Config):
        super().__init__(settings)
        self.messages: list[IncomingMessage] = []
        self.sent: list[str] = []

    def _receive(self, handler: IncomingHandler) -> None:
        for message in self.messages:
            handler(message)

    def _send(self, incoming: IncomingMessage, text: str) -> None:
        self.sent.append(text)
