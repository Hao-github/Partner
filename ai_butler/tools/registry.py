import json
import logging
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from jsonschema import ValidationError, validate
from mcp import StdioServerParameters
from mcp.types import RequestParamsMeta, TextContent
from mcp.types import Tool as MCPTool

from ..config import PROJECT_DIR, Config, config
from ._mcp import MCPClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tool:
    descriptor: MCPTool
    client: MCPClient
    contextual: bool = False

    @property
    def schema(self) -> dict[str, Any]:
        parameters = self.descriptor.input_schema.copy()
        parameters.setdefault("additionalProperties", False)
        return {
            "type": "function",
            "function": {
                "name": self.descriptor.name,
                "description": self.descriptor.description or "",
                "parameters": parameters,
            },
        }


class ToolRegistry:
    """MCP 发现结果同时用于模型描述和执行分发；按需建立会话。"""

    def __init__(self, settings: Config = config):
        self._builtin = MCPClient(
            StdioServerParameters(
                command=sys.executable,
                args=["-X", "utf8", "-m", "ai_butler.tools.mcp_server"],
                cwd=str(PROJECT_DIR),
                env={"PYTHONUTF8": "1"},
            ),
            settings.timeout,
        )
        key = settings.options.get("AMAP_MAPS_API_KEY", "").strip()
        self._amap = (
            MCPClient(f"https://mcp.amap.com/mcp?{urlencode({'key': key})}", settings.timeout)
            if key
            else None
        )
        self._tools: dict[str, Tool] = {}
        self._loaded: set[MCPClient] = set()

    def _load(
        self, client: MCPClient, *, contextual: bool = False, allowed: set[str] | None = None
    ) -> None:
        if client in self._loaded:
            return
        discovered: dict[str, Tool] = {}
        for descriptor in client.list_tools():
            if allowed is not None and descriptor.name not in allowed:
                continue
            if descriptor.name in self._tools or descriptor.name in discovered:
                raise RuntimeError(f"MCP 工具名称重复：{descriptor.name}。")
            discovered[descriptor.name] = Tool(descriptor, client, contextual)
        self._tools.update(discovered)
        self._loaded.add(client)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        self._load(self._builtin, contextual=True)
        if self._amap is not None:
            try:
                self._load(self._amap, allowed={"maps_weather"})
            except RuntimeError:
                logger.warning("mcp_weather_unavailable")
        return [tool.schema for tool in self._tools.values()]

    def execute(self, name: str, arguments: str, settings: Config = config) -> str:
        try:
            params = json.loads(arguments)
            if not isinstance(params, dict):
                raise TypeError
        except (ValueError, TypeError):
            return json.dumps({"error": "参数必须是 JSON 对象。"}, ensure_ascii=False)
        self._load(self._builtin, contextual=True)
        if name not in self._tools and self._amap is not None:
            self._load(self._amap, allowed={"maps_weather"})
        if (tool := self._tools.get(name)) is None:
            return json.dumps({"error": "未知工具。"}, ensure_ascii=False)
        try:
            validate(params, tool.schema["function"]["parameters"])
        except ValidationError:
            return json.dumps({"error": "工具参数不符合要求。"}, ensure_ascii=False)
        meta: RequestParamsMeta | None = (
            {
                "gptpartner": {
                    "provider": settings.provider,
                    "model": settings.model,
                    "config_version": settings.config_version,
                    "environment": settings.options.get("CONDA_DEFAULT_ENV", ""),
                }
            }
            if tool.contextual
            else None
        )
        result = tool.client.call(name, params, meta)
        if result.is_error:
            return json.dumps({"error": "工具执行失败，请检查参数或服务状态。"}, ensure_ascii=False)
        if result.structured_content is not None:
            return json.dumps(result.structured_content, ensure_ascii=False)
        return "\n".join(item.text for item in result.content if isinstance(item, TextContent))

    def close(self) -> None:
        if self._amap is not None:
            self._amap.close()
        self._builtin.close()
