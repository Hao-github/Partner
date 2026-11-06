import logging
from contextlib import ExitStack
from functools import partial
from typing import Any

from anyio import BrokenResourceError, EndOfStream
from anyio.from_thread import BlockingPortal, start_blocking_portal
from httpx2 import HTTPError
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import StreamableHTTPError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, RequestParamsMeta, Tool

logger = logging.getLogger(__name__)
_MCP_ERRORS = (
    OSError,
    RuntimeError,
    ValueError,
    ExceptionGroup,
    BrokenResourceError,
    EndOfStream,
    HTTPError,
    StreamableHTTPError,
    MCPError,
)


class _TransportLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """屏蔽传输正文和 URL，只保留不含凭据的固定警告。"""
        if record.levelno < logging.WARNING:
            return False
        record.msg = "mcp_transport_warning"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


class MCPClient:
    """将异步 MCP 会话适配到同步 Agent，持有传输、线程和关闭边界。"""

    def __init__(self, server: StdioServerParameters | str, timeout: float):
        """保存连接参数并安装可移除的日志过滤器，不立即连接。"""
        self._server = server
        self._timeout = timeout
        self._resources = ExitStack()
        self._connection: tuple[BlockingPortal, Client] | None = None
        self._closed = False
        # SDK 的调试正文和 HTTP URL 可能含凭据；只保留固定警告事件。
        transport_logs = _TransportLogs()
        names = [
            "httpx2",
            "httpcore2.connection",
            "httpcore2.http11",
            "httpcore2.http2",
            "httpcore2.proxy",
            "httpcore2.socks",
            "mcp.client.streamable_http",
            "mcp.client.client",
            "mcp.shared.jsonrpc_dispatcher",
            "mcp.client.stdio",
        ]
        for name in names:
            target = logging.getLogger(name)
            target.addFilter(transport_logs)
            self._resources.callback(target.removeFilter, transport_logs)

    def _connect(self) -> tuple[BlockingPortal, Client]:
        """首次使用时建立后台会话并复用，连接失败则释放所有资源。"""
        if self._closed:
            raise RuntimeError("MCP 工具服务已关闭。")
        if self._connection is None:
            try:
                portal = self._resources.enter_context(start_blocking_portal())
                client = self._resources.enter_context(
                    portal.wrap_async_context_manager(
                        Client(self._server, read_timeout_seconds=self._timeout)
                    )
                )
                self._connection = portal, client
            except _MCP_ERRORS:
                self.close()
                raise RuntimeError("MCP 服务连接失败，请检查服务配置和网络。") from None
        return self._connection

    def list_tools(self) -> list[Tool]:
        """分页发现工具，限制总页数并统一转换传输错误。"""
        portal, client = self._connect()
        try:
            tools: list[Tool] = []
            cursor = None
            for _ in range(100):
                page = portal.call(partial(client.list_tools, cursor=cursor))
                tools.extend(page.tools)
                if (cursor := page.next_cursor) is None:
                    return tools
            raise RuntimeError("MCP 工具分页超出上限。")
        except _MCP_ERRORS:
            raise RuntimeError("MCP 工具发现失败，请检查服务状态。") from None

    def call(
        self, name: str, arguments: dict[str, Any], meta: RequestParamsMeta | None = None
    ) -> CallToolResult:
        """在后台异步会话执行工具，将传输失败转换为安全提示。"""
        portal, client = self._connect()
        try:
            return portal.call(partial(client.call_tool, name, arguments, meta=meta))
        except _MCP_ERRORS:
            raise RuntimeError("MCP 工具调用失败或超时，请稍后重试。") from None

    def close(self) -> None:
        """关闭会话、线程和日志过滤器，可重复调用。"""
        if self._closed:
            return
        self._closed = True
        try:
            self._resources.close()
        except _MCP_ERRORS:
            logger.warning("mcp_close_failed")
        finally:
            self._connection = None
