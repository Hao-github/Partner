import json
from unittest.mock import Mock

from ai_butler.models import IncomingMessage
from ai_butler.tools.registry import ToolRegistry
from tests.helpers import ProjectTest, tool_message


class AgentTests(ProjectTest):
    def test_provided_history_is_used_without_being_modified(self):
        provider = Mock()
        provider.complete.return_value = {"role": "assistant", "content": "你好，小华"}
        history = [
            {"role": "user", "content": "我叫小华"},
            {"role": "assistant", "content": "收到"},
        ]
        before = list(history)
        incoming = IncomingMessage("test", "user", "a", "继续")
        result = self.create_agent(provider)._respond(incoming, history)
        messages = provider.complete.call_args.args[0]
        self.assertEqual(messages[1:3], before)
        self.assertEqual(history, before)
        self.assertEqual(result.text, "你好，小华")
        self.assertEqual(result.messages[0], {"role": "user", "content": "继续"})
        self.assertFalse(self.settings.db_path.exists())

    def test_tool_results_are_sent_back_and_returned_in_complete_turn(self):
        provider = Mock()
        provider.complete.side_effect = [
            tool_message("one", "two"),
            {"role": "assistant", "content": "版本已获取。"},
        ]
        result = self.create_agent(provider, max_tool_rounds=1)._respond(
            IncomingMessage("test", "user", "a", "查询版本"), []
        )
        messages = provider.complete.call_args.args[0]
        self.assertEqual(
            [m["tool_call_id"] for m in messages if m["role"] == "tool"], ["one", "two"]
        )
        self.assertEqual(
            json.loads(messages[-1]["content"])["model"]["version"], self.settings.model
        )
        self.assertEqual(len(result.messages), 5)
        self.assertEqual(result.text, "版本已获取。")

    def test_failure_mid_turn_does_not_modify_history(self):
        history = [{"role": "user", "content": "之前"}, {"role": "assistant", "content": "收到"}]
        before = list(history)
        provider = Mock()
        provider.complete.side_effect = [
            tool_message("call_1"),
            RuntimeError("超时"),
        ]
        with self.assertRaises(RuntimeError):
            self.create_agent(provider)._respond(
                IncomingMessage("test", "user", "a", "版本"), history
            )
        self.assertEqual(history, before)
        self.assertFalse(self.settings.db_path.exists())

    def test_tool_loop_limit_does_not_return_incomplete_turn(self):
        provider = Mock()
        provider.complete.return_value = tool_message("call_1")
        agent = self.create_agent(provider, max_tool_rounds=1)
        with self.assertRaisesRegex(RuntimeError, "上限"):
            agent._respond(IncomingMessage("test", "user", "a", "版本"), [])
        self.assertEqual(provider.complete.call_count, 2)
        self.assertFalse(self.settings.db_path.exists())


class ToolTests(ProjectTest):
    def test_unknown_tool_and_invalid_arguments_are_rejected(self):
        tools = ToolRegistry(self.settings)
        self.addCleanup(tools.close)
        for name in ("run_shell", "get_beijing_time"):
            with self.subTest(name=name):
                self.assertEqual(json.loads(tools.execute(name, "{}")), {"error": "未知工具。"})
        for arguments in ("not-json", "[]", "null", '{"command":"anything"}'):
            with self.subTest(arguments=arguments):
                self.assertIn("error", json.loads(tools.execute("get_version", arguments)))
