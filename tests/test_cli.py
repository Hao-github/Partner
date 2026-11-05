from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from unittest.mock import patch

from main import main
from tests.helpers import ProjectTest


class CLITests(ProjectTest):
    def run_cli(self, inputs, *, settings=None, response=None):
        output = StringIO()
        with (
            patch("main.config", settings or self.settings),
            patch("ai_butler.providers.DeepSeekProvider") as provider,
            patch("builtins.input", side_effect=inputs),
            redirect_stdout(output),
        ):
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
        status, output, _ = self.run_cli([], settings=replace(self.settings, deepseek_api_key=""))
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
        with patch("ai_butler.app.Agent.reply", side_effect=RuntimeError("网络错误")):
            status, output, _ = self.run_cli(["你好", "/exit"])
        self.assertEqual(status, 0)
        self.assertIn("网络错误", output)
