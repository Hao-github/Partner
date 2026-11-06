from dataclasses import replace
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from ..config import config
from .version import get_version as version_info


def create_server() -> MCPServer:
    """独立 stdio 服务；工具函数生成 schema 和执行入口。"""
    server = MCPServer("GPTPartner tools")

    @server.tool()
    def get_version(ctx: Context) -> dict[str, Any]:
        """查询管家应用、配置、当前会话模型标识及 Python/系统/MCP 环境版本。"""
        context = (ctx.request_context.meta or {}).get("gptpartner", {})
        if not isinstance(context, dict):
            raise TypeError("版本查询上下文必须是对象。")
        settings = replace(
            config,
            provider=str(context.get("provider", config.provider)),
            model=str(context.get("model", config.model)),
            config_version=str(context.get("config_version", config.config_version)),
            options={"CONDA_DEFAULT_ENV": str(context.get("environment", ""))},
        )
        return version_info(settings)

    return server


if __name__ == "__main__":
    create_server().run()
