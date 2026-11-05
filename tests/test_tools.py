import json
import unittest
from datetime import UTC, datetime, timedelta

from ai_butler.tools.clock import get_beijing_time
from ai_butler.tools.registry import execute_tool


class ToolTests(unittest.TestCase):
    def test_beijing_time_is_current_and_has_correct_offset(self):
        before = datetime.now(UTC)
        output = get_beijing_time()
        actual = datetime.fromisoformat(output["datetime"])
        self.assertEqual(actual.utcoffset(), timedelta(hours=8))
        self.assertEqual(output["timezone"], "Asia/Shanghai")
        self.assertLessEqual(before - timedelta(seconds=1), actual)
        self.assertLessEqual(actual, datetime.now(UTC))

    def test_unknown_tool_and_invalid_arguments_are_rejected(self):
        self.assertIn("error", json.loads(execute_tool("run_shell", "{}")))
        for arguments in ("not-json", "[]", "null", '{"command":"anything"}'):
            with self.subTest(arguments=arguments):
                self.assertIn("error", json.loads(execute_tool("get_beijing_time", arguments)))
