from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from unittest.mock import patch

from ai_butler import Butler
from ai_butler.models import IncomingMessage, ModelSelection
from main import main
from tests.helpers import ProjectTest
from tests.test_channels import RecordingChannel


class ModelSwitchTests(ProjectTest):
    def run_cli(self, inputs, *, settings=None):
        output = StringIO()
        settings = settings or replace(self.settings, openai_api_key="test-openai")
        with (
            patch("main.config", settings),
            patch("ai_butler.providers.DeepSeekProvider") as deepseek,
            patch("ai_butler.providers.OpenAIProvider") as openai,
            patch("builtins.input", side_effect=inputs),
            redirect_stdout(output),
        ):
            deepseek.return_value.complete.return_value = {
                "role": "assistant",
                "content": "DeepSeek 回答",
            }
            openai.return_value.complete.return_value = {
                "role": "assistant",
                "content": "OpenAI 回答",
            }
            status = main([])
        return status, output.getvalue(), deepseek, openai

    def test_switching_model_preserves_history_without_saving_commands_as_turns(self):
        status, output, deepseek, openai = self.run_cli(
            [
                "第一条",
                "/model openai test-openai",
                "第二条",
                "/model next-openai",
                "第三条",
                "/model",
                "/exit",
            ]
        )
        self.assertEqual(status, 0)
        deepseek.return_value.complete.assert_called_once()
        self.assertEqual(openai.return_value.complete.call_count, 2)
        self.assertEqual(
            [call.args[0].model for call in openai.call_args_list], ["test-openai", "next-openai"]
        )
        messages = openai.return_value.complete.call_args.args[0]
        self.assertEqual(
            [m["content"] for m in messages if m["role"] == "user"], ["第一条", "第二条", "第三条"]
        )
        self.assertIn("当前模型：openai / next-openai", output)
        store = self.store()
        self.assertEqual(len(store.load("live:default")), 6)
        self.assertEqual(store.get_model("live:default"), ModelSelection("openai", "next-openai"))
        self.assertEqual(self.settings.provider, "deepseek")

    def test_sessions_have_independent_models_and_can_restore_startup_default(self):
        status, output, deepseek, openai = self.run_cli(
            [
                "/model openai test-openai",
                "默认会话",
                "/session other",
                "/model",
                "另一会话",
                "/session default",
                "/model default",
                "恢复后",
                "/exit",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("当前模型：deepseek / deepseek-flash", output)
        self.assertEqual(deepseek.return_value.complete.call_count, 2)
        openai.return_value.complete.assert_called_once()
        store = self.store()
        self.assertEqual(
            store.get_model("live:default"), ModelSelection("deepseek", "deepseek-flash")
        )
        self.assertIsNone(store.get_model("live:other"))
        self.assertEqual(len(store.load("live:other")), 2)

    def test_restart_restores_session_model(self):
        status, _, deepseek, openai = self.run_cli(["/model openai test-openai", "/exit"])
        self.assertEqual(status, 0)
        deepseek.return_value.complete.assert_not_called()
        openai.return_value.complete.assert_not_called()
        status, output, deepseek, openai = self.run_cli(["/model", "继续", "/exit"])
        self.assertEqual(status, 0)
        self.assertIn("当前模型：openai / test-openai", output)
        openai.return_value.complete.assert_called_once()
        deepseek.return_value.complete.assert_not_called()

    def test_rejected_switch_keeps_previous_model(self):
        status, output, deepseek, openai = self.run_cli(
            [
                "/model openai test-openai",
                "/model unknown test-model",
                "/model a b c",
                "继续",
                "/exit",
            ],
            settings=self.settings,
        )
        self.assertEqual(status, 0)
        self.assertIn("OPENAI_API_KEY", output)
        self.assertIn("BUTLER_PROVIDER", output)
        self.assertIn("用法：/model", output)
        self.assertIsNone(self.store().get_model("live:default"))
        openai.assert_not_called()
        deepseek.return_value.complete.assert_called_once()

    def test_missing_credentials_for_restored_model_can_be_recovered_in_chat(self):
        self.run_cli(["/model openai test-openai", "/exit"])
        status, output, deepseek, openai = self.run_cli(
            ["继续", "/model default", "恢复", "/exit"], settings=self.settings
        )
        self.assertEqual(status, 0)
        self.assertIn("模型配置不可用", output)
        self.assertIn("已切换模型：deepseek", output)
        deepseek.return_value.complete.assert_called_once()
        openai.assert_not_called()
        self.assertEqual(len(self.store().load("live:default")), 2)

    def test_redelivering_old_qq_switch_does_not_revert_new_selection(self):
        settings = replace(self.settings, openai_api_key="test-openai")
        channel = RecordingChannel(settings)
        session = "qq:123:c2c:owner"
        first = IncomingMessage("qq", "owner", session, "/model openai first-model", "1")
        channel.messages = [
            first,
            IncomingMessage("qq", "owner", session, "/model deepseek second-model", "2"),
            first,
            IncomingMessage("qq", "owner", session, "继续", "3"),
        ]
        with (
            patch("ai_butler.app.create_channel", return_value=channel),
            patch("ai_butler.providers.DeepSeekProvider") as deepseek,
            patch("ai_butler.providers.OpenAIProvider") as openai,
        ):
            deepseek.return_value.complete.return_value = {"role": "assistant", "content": "收到"}
            Butler(channel="qq", settings=settings).run()
        self.assertEqual(len(channel.sent), 3)
        self.assertEqual(
            self.store().get_model(session), ModelSelection("deepseek", "second-model")
        )
        self.assertEqual(deepseek.call_args.args[0].model, "second-model")
        deepseek.return_value.complete.assert_called_once()
        openai.return_value.complete.assert_not_called()

    def test_chat_text_mentioning_model_command_is_sent_to_model(self):
        status, _, deepseek, _ = self.run_cli(["解释 /model 这个命令", "/exit"])
        self.assertEqual(status, 0)
        deepseek.return_value.complete.assert_called_once()
