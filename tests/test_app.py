from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from threading import Event
from unittest.mock import Mock, patch

from ai_butler import Butler
from ai_butler.channels import create_channel, inspect_channel
from ai_butler.models import IncomingMessage, Reply
from ai_butler.providers import create_provider
from main import main
from tests.helpers import ProjectTest


class AppTests(ProjectTest):
    def test_cli_runtime_options_select_model_without_mutating_shared_config(self):
        settings = replace(self.settings, openai_api_key="test-openai")
        with (
            patch("main.config", settings),
            patch("ai_butler.app.create_provider", wraps=create_provider) as factory,
            patch(
                "ai_butler.providers.chat_completions.ChatCompletionsProvider.complete"
            ) as complete,
            patch("builtins.input", side_effect=["测试消息", "/exit"]),
            redirect_stdout(StringIO()),
        ):
            complete.return_value = {"role": "assistant", "content": "测试回答"}
            status = main(["--channel", "cli", "--provider", "openai", "--model", "test-model"])
        self.assertEqual(status, 0)
        selected = factory.call_args.args[0]
        self.assertEqual(selected.provider, "openai")
        self.assertEqual(selected.model, "test-model")
        self.assertEqual(selected.base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.provider, "deepseek")
        self.assertEqual(settings.model, "deepseek-flash")
        self.assertEqual(len(self.store().load("live:default")), 2)

    @patch("ai_butler.channels.qq.channel._QQGateway")
    @patch("ai_butler.channels.qq.channel._QQClient")
    def test_qq_app_preserves_context_and_hides_transport_from_provider(self, client, gateway):
        settings = replace(
            self.settings,
            qq_app_id="123",
            qq_app_secret="test-secret",
            qq_allowed_users=("owner",),
            qq_min_interval=0,
        )
        sent = Event()

        def send(*args):
            if client.return_value.send_text.call_count == 2:
                sent.set()

        def run():
            accept = gateway.call_args.args[1]
            accept({"id": "1", "author": {"user_openid": "owner"}, "content": "第一条"})
            accept({"id": "2", "author": {"user_openid": "owner"}, "content": "第二条"})
            self.assertTrue(sent.wait(5), "后台回复未完成")

        client.return_value.send_text.side_effect = send
        gateway.return_value.run.side_effect = run
        with patch("ai_butler.providers.DeepSeekProvider") as provider:
            provider.return_value.complete.return_value = {"role": "assistant", "content": "收到"}
            Butler(channel="qq", settings=settings).run()
        self.assertEqual(client.return_value.send_text.call_count, 2)
        messages = provider.return_value.complete.call_args.args[0]
        self.assertEqual(
            [m["content"] for m in messages if m["role"] == "user"], ["第一条", "第二条"]
        )
        self.assertNotIn("user_openid", str(messages))
        self.assertEqual(len(self.store().load("qq:123:c2c:owner")), 4)
        gateway.return_value.close.assert_called_once()

    def test_run_closes_channel_even_when_receive_is_interrupted(self):
        with patch("ai_butler.app.create_channel") as factory:
            channel = factory.return_value
            channel.receive.side_effect = KeyboardInterrupt()
            app = Butler(settings=self.settings)
            with self.assertRaises(KeyboardInterrupt):
                app.run()
        channel.close.assert_called_once()

    def test_application_logs_metadata_without_message_body_or_secret(self):
        with (
            patch("ai_butler.app.create_provider") as provider,
            patch("builtins.input", side_effect=["private-body", "/exit"]),
            redirect_stdout(StringIO()),
            self.assertLogs("ai_butler", level="INFO") as logs,
        ):
            provider.return_value.complete.return_value = {
                "role": "assistant",
                "content": "private-reply",
            }
            Butler(settings=self.settings).run()
        output = str(logs.output)
        self.assertIn("app_started", output)
        self.assertIn("message_received", output)
        self.assertIn("app_stopped", output)
        for private in (
            "private-user",
            "private-session",
            "private-body",
            "private-reply",
            "test-secret",
        ):
            self.assertNotIn(private, output)

    def test_channel_is_usable_without_a_provider(self):
        handler = Mock(return_value=Reply("自定义回复"))
        channel = create_channel("cli", settings=self.settings)
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
            create_channel("unknown", settings=self.settings)
        with self.assertRaisesRegex(ValueError, "只有 QQ"):
            inspect_channel("cli", settings=self.settings)
