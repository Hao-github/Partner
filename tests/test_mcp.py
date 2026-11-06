import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

from mcp.types import CallToolResult, TextContent, Tool

from ai_butler.models import ModelSelection
from ai_butler.tools._mcp import MCPClient
from ai_butler.tools.registry import ToolRegistry
from tests.helpers import ProjectTest


class MCPTests(ProjectTest):
    def registry(self, **changes):
        registry = ToolRegistry(replace(self.settings, **changes))
        self.addCleanup(registry.close)
        return registry

    def test_stdio_discovery_execution_context_and_worker_lifecycle(self):
        registry = self.registry(
            config_version="v2",
            options={"CONDA_DEFAULT_ENV": "gptpartner", "PRIVATE_KEY": "hidden-key"},
        )
        self.assertEqual(
            [tool["function"]["name"] for tool in registry.schemas],
            ["get_version"],
        )
        selected = ModelSelection("openai", "session-model")
        with ThreadPoolExecutor(max_workers=1) as worker:
            result = worker.submit(registry.execute, "get_version", "{}", selected).result(15)
        data = json.loads(result)
        self.assertEqual(data["config_version"], "v2")
        self.assertEqual(
            data["model"],
            {
                "provider": "openai",
                "version": "session-model",
                "version_source": "configured_model_id",
            },
        )
        self.assertEqual(data["environment"]["conda"], "gptpartner")
        self.assertTrue(data["environment"]["python"])
        self.assertNotIn("hidden-key", result)
        self.assertNotIn("PRIVATE_KEY", result)
        self.assertNotIn(str(self.root), result)
        registry.close()
        registry.close()
        with self.assertRaisesRegex(RuntimeError, "关闭"):
            registry.execute("get_version", "{}")

    def test_discovery_duplicate_is_rejected_without_partial_registration(self):
        registry = self.registry()
        tool = Tool(name="duplicate", input_schema={"type": "object"})
        with (
            patch.object(registry._builtin, "list_tools", return_value=[tool, tool]),
            self.assertRaisesRegex(RuntimeError, "重复"),
        ):
            _ = registry.schemas
        self.assertEqual(registry._tools, {})

    def test_only_weather_is_exposed_from_amap_and_arguments_are_validated(self):
        registry = self.registry(options={"AMAP_MAPS_API_KEY": "test-amap-key"})
        weather = Tool(
            name="maps_weather",
            input_schema={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        )
        remote = Mock()
        remote.list_tools.return_value = [weather, Tool(name="maps_other", input_schema={})]
        remote.call.return_value = CallToolResult(content=[], structured_content={"city": "北京"})
        if registry._amap is not None:
            registry._amap.close()
        registry._amap = remote
        names = [item["function"]["name"] for item in registry.schemas]
        self.assertIn("maps_weather", names)
        self.assertNotIn("maps_other", names)
        for arguments in ("{}", '{"city":1}', '{"city":"北京","extra":true}'):
            self.assertIn("error", json.loads(registry.execute("maps_weather", arguments)))
        remote.call.assert_not_called()
        output = registry.execute("maps_weather", '{"city":"北京"}')
        self.assertEqual(json.loads(output), {"city": "北京"})
        remote.call.assert_called_once_with("maps_weather", {"city": "北京"}, None)

    def test_weather_discovery_failure_keeps_local_tools_and_version_available(self):
        registry = self.registry()
        registry._amap = Mock()
        registry._amap.list_tools.side_effect = RuntimeError("service unavailable")
        with self.assertLogs("ai_butler.tools.registry", "WARNING"):
            self.assertEqual(len(registry.schemas), 1)
        result = registry.execute("get_version", "{}")
        self.assertEqual(json.loads(result)["model"]["version"], self.settings.model)

    def test_mcp_timeout_does_not_expose_transport_error(self):
        registry = self.registry()
        _ = registry.schemas
        with (
            patch("mcp.Client.call_tool", AsyncMock(side_effect=TimeoutError("private-url-key"))),
            self.assertRaisesRegex(RuntimeError, "超时") as error,
        ):
            registry.execute("get_version", "{}")
        self.assertNotIn("private-url-key", str(error.exception))

    def test_remote_error_is_hidden_and_text_result_remains_supported(self):
        registry = self.registry()
        _ = registry.schemas
        with patch.object(registry._builtin, "call") as call:
            call.return_value = CallToolResult(
                content=[TextContent(type="text", text="remote-secret")], is_error=True
            )
            result = registry.execute("get_version", "{}")
            self.assertIn("error", json.loads(result))
            self.assertNotIn("remote-secret", result)
            call.return_value = CallToolResult(content=[TextContent(type="text", text="plain")])
            self.assertEqual(registry.execute("get_version", "{}"), "plain")

    def test_http_logs_redact_key_and_exception_and_filter_is_removed_on_close(self):
        target = logging.getLogger("httpx2")
        before = list(target.filters)
        client = MCPClient("https://example.invalid?key=hidden", 1)
        self.addCleanup(client.close)
        with self.assertLogs("httpx2", "INFO") as logs:
            try:
                raise RuntimeError("hidden")
            except RuntimeError:
                target.exception("request %s", "https://example.invalid?key=hidden")
        self.assertNotIn("hidden", str(logs.output))
        self.assertNotIn("https://example.invalid", str(logs.output))
        self.assertNotIn("Traceback", str(logs.output))
        client.close()
        self.assertEqual(target.filters, before)
