from dataclasses import replace
from unittest.mock import Mock, patch

from ai_butler.channels import Channel, MessageHandler
from ai_butler.config import Config
from ai_butler.core.agent import Agent
from ai_butler.models import IncomingMessage
from tests.helpers import ProjectTest


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


class ChannelTests(ProjectTest):
    def channel(self, **changes):
        channel = RecordingChannel(replace(self.settings, **changes))
        self.addCleanup(channel.close)
        return channel

    def agent(self):
        self.provider = Mock()
        self.provider.complete.return_value = {"role": "assistant", "content": "收到"}
        return Agent(self.provider, self.settings)

    def incoming(self, text="你好", session="test:a", message=""):
        return IncomingMessage("test", "user", session, text, message)

    def test_restart_preserves_context_and_sessions_are_isolated(self):
        agent = self.agent()
        first = self.channel()
        first.messages = [self.incoming("我叫小华")]
        first.receive(agent.reply)
        first.close()
        second = self.channel()
        second.messages = [self.incoming("继续")]
        second.receive(agent.reply)
        messages = self.provider.complete.call_args.args[0]
        self.assertEqual(messages[1], {"role": "user", "content": "我叫小华"})
        self.assertEqual(second.history("test:b"), [])
        self.assertEqual(len(second.history("test:a")), 4)

    def test_history_window_keeps_complete_turns_in_order(self):
        channel = self.channel(history_turns=2)
        channel.messages = [
            self.incoming(text) for text in ("第一条", "第二条", "第三条", "第四条")
        ]
        channel.receive(self.agent().reply)
        messages = self.provider.complete.call_args.args[0]
        self.assertEqual(
            [m["content"] for m in messages if m["role"] == "user"], ["第二条", "第三条", "第四条"]
        )
        self.assertEqual(len(channel.history("test:a")), 4)
        self.assertEqual(len(self.store().load("test:a")), 8)

    def test_delivery_deduplication_is_shared_by_channels_and_survives_restart(self):
        agent = self.agent()
        incoming = self.incoming(message="same-message")
        first = self.channel()
        first.messages = [incoming, incoming]
        first.receive(agent.reply)
        second = self.channel()
        second.messages = [incoming]
        second.receive(agent.reply)
        self.provider.complete.assert_called_once()
        self.assertEqual(first.sent, ["收到"])
        self.assertEqual(second.sent, [])
        self.assertEqual(len(second.history(incoming.session_id)), 2)

    def test_failed_send_reuses_cached_turn_without_calling_model_again(self):
        channel = self.channel()
        agent = self.agent()
        incoming = self.incoming(message="retry")
        channel.messages = [incoming]
        with (
            patch.object(channel, "_send", side_effect=RuntimeError("network")),
            self.assertRaises(RuntimeError),
        ):
            channel.receive(agent.reply)
        cached = self.store().get_delivery(incoming)
        self.assertEqual(cached and (cached.reply, cached.sent), ("收到", False))
        channel.receive(agent.reply)
        self.provider.complete.assert_called_once()
        self.assertEqual(channel.sent, ["收到"])
        self.assertEqual(len(channel.history(incoming.session_id)), 2)
        cached = self.store().get_delivery(incoming)
        self.assertEqual(cached and cached.sent, True)

    def test_messages_without_platform_id_are_not_deduplicated(self):
        channel = self.channel()
        incoming = self.incoming()
        channel.messages = [incoming, incoming]
        channel.receive(self.agent().reply)
        self.assertEqual(self.provider.complete.call_count, 2)
        self.assertEqual(len(channel.history(incoming.session_id)), 4)

    def test_model_failure_keeps_previous_history_and_is_retryable(self):
        channel = self.channel()
        agent = self.agent()
        channel.messages = [self.incoming("之前")]
        channel.receive(agent.reply)
        before = channel.history("test:a")
        incoming = self.incoming("失败轮次", message="failed")
        channel.messages = [incoming]
        self.provider.complete.side_effect = RuntimeError("request failed")
        with self.assertRaises(RuntimeError):
            channel.receive(agent.reply)
        self.assertEqual(channel.history("test:a"), before)
        self.assertIsNone(self.store().get_delivery(incoming))

    def test_storage_failure_does_not_require_platform_to_handle_sqlite_errors(self):
        blocked = self.root / "blocked"
        blocked.write_text("fixture", encoding="utf-8")
        channel = self.channel(db_path=blocked / "sessions.sqlite3")
        channel.messages = [self.incoming()]
        handler = Mock()
        with self.assertRaisesRegex(RuntimeError, "本地会话存取失败"):
            channel.receive(handler)
        with self.assertRaisesRegex(RuntimeError, "本地会话存取失败"):
            channel.history("test:a")
        handler.assert_not_called()
