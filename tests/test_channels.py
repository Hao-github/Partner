from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from unittest.mock import Mock, patch

from ai_butler import Agent
from ai_butler.channels import _create_channel
from ai_butler.models import IncomingMessage, Reply
from main import main
from tests.helpers import ProjectTest, RecordingChannel, configure_provider_mock


class ChannelTests(ProjectTest):
    def channel(self, **changes):
        channel = RecordingChannel(replace(self.settings, **changes))
        self.addCleanup(channel.close)
        return channel

    def agent(self):
        self.provider = Mock()
        self.provider.complete.return_value = {"role": "assistant", "content": "收到"}
        return self.create_agent(self.provider)

    def incoming(self, text="你好", session="test:a", message=""):
        return IncomingMessage("test", "user", session, text, message)

    def test_restart_preserves_context_and_sessions_are_isolated(self):
        agent = self.agent()
        first = self.channel()
        first.messages = [self.incoming("我叫小华")]
        first.receive(agent._respond)
        first.close()
        second = self.channel()
        second.messages = [self.incoming("继续")]
        second.receive(agent._respond)
        messages = self.provider.complete.call_args.args[0]
        self.assertEqual(messages[1], {"role": "user", "content": "我叫小华"})
        self.assertEqual(second.history("test:b"), [])
        self.assertEqual(len(second.history("test:a")), 4)

    def test_history_window_keeps_complete_turns_in_order(self):
        channel = self.channel(history_turns=2)
        channel.messages = [
            self.incoming(text) for text in ("第一条", "第二条", "第三条", "第四条")
        ]
        channel.receive(self.agent()._respond)
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
        first.receive(agent._respond)
        second = self.channel()
        second.messages = [incoming]
        second.receive(agent._respond)
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
            channel.receive(agent._respond)
        cached = self.store().get_delivery(incoming)
        self.assertEqual(cached and (cached.reply, cached.sent), ("收到", False))
        channel.receive(agent._respond)
        self.provider.complete.assert_called_once()
        self.assertEqual(channel.sent, ["收到"])
        self.assertEqual(len(channel.history(incoming.session_id)), 2)
        cached = self.store().get_delivery(incoming)
        self.assertEqual(cached and cached.sent, True)

    def test_messages_without_platform_id_are_not_deduplicated(self):
        channel = self.channel()
        incoming = self.incoming()
        channel.messages = [incoming, incoming]
        channel.receive(self.agent()._respond)
        self.assertEqual(self.provider.complete.call_count, 2)
        self.assertEqual(len(channel.history(incoming.session_id)), 4)

    def test_model_failure_keeps_previous_history_and_is_retryable(self):
        channel = self.channel()
        agent = self.agent()
        channel.messages = [self.incoming("之前")]
        channel.receive(agent._respond)
        before = channel.history("test:a")
        incoming = self.incoming("失败轮次", message="failed")
        channel.messages = [incoming]
        self.provider.complete.side_effect = RuntimeError("request failed")
        with self.assertRaises(RuntimeError):
            channel.receive(agent._respond)
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

    def test_channel_is_usable_without_a_provider(self):
        handler = Mock(return_value=Reply("自定义回复"))
        channel = _create_channel("cli", settings=self.settings)
        self.addCleanup(channel.close)
        output = StringIO()
        with patch("builtins.input", side_effect=["获取消息", "/exit"]), redirect_stdout(output):
            channel.receive(handler)
        handler.assert_called_once_with(
            IncomingMessage("cli", "local", "live:default", "获取消息"), []
        )
        self.assertIn("管家> 自定义回复", output.getvalue())

    def test_unknown_channel_and_unsupported_diagnostics_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "不支持的渠道"):
            _create_channel("unknown", settings=self.settings)
        with self.assertRaisesRegex(ValueError, "不支持渠道诊断"):
            Agent.inspect("cli", settings=self.settings)


class CLITests(ProjectTest):
    def run_cli(self, inputs, *, settings=None, response=None):
        output = StringIO()
        with (
            patch("main.config", settings or self.settings),
            patch("ai_butler.providers._DeepSeekProvider") as provider,
            patch("builtins.input", side_effect=inputs),
            redirect_stdout(output),
        ):
            configure_provider_mock(provider)
            provider.return_value.complete.return_value = response or {
                "role": "assistant",
                "content": "你好，小华",
            }
            status = main([])
        return status, output.getvalue(), provider.return_value

    def test_chat_history_switching_and_restart(self):
        status, output, _ = self.run_cli(["我叫小华", "/session other", "/history", "/exit"])
        self.assertEqual(status, 0)
        self.assertIn("当前会话暂无记录", output)
        status, _, provider = self.run_cli(["继续", "/exit"])
        self.assertEqual(status, 0)
        self.assertEqual(provider.complete.call_args.args[0][1]["content"], "我叫小华")

    def test_missing_key_does_not_create_database(self):
        status, output, _ = self.run_cli([], settings=replace(self.settings, options={}))
        self.assertEqual(status, 2)
        self.assertIn("DEEPSEEK_API_KEY", output)
        self.assertFalse(self.settings.db_path.exists())

    def test_removed_demo_option_is_rejected(self):
        with (
            redirect_stdout(StringIO()),
            patch("sys.stderr", new_callable=StringIO),
            self.assertRaises(SystemExit) as error,
        ):
            main(["--demo"])
        self.assertEqual(error.exception.code, 2)

    def test_eof_commands_and_model_error_are_recoverable(self):
        status, output, _ = self.run_cli(["", "/unknown", "/session bad/name", "/help", EOFError()])
        self.assertEqual(status, 0)
        self.assertIn("未知命令", output)
        with patch(
            "ai_butler.core.agent.Agent._complete_turn", side_effect=RuntimeError("网络错误")
        ):
            status, output, _ = self.run_cli(["你好", "/exit"])
        self.assertEqual(status, 0)
        self.assertIn("网络错误", output)
