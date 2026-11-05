import json
from typing import Any
from urllib.request import Request

from ..models import Message
from ._base import Provider


class DeepSeekProvider(Provider):
    """内部 DeepSeek 适配：维护请求参数、认证、响应格式及错误提示。"""

    default_model = "deepseek-flash"
    default_base_url = "https://api.deepseek.com"

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        request = Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": self.config.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "stream": False,
                    "thinking": {"type": "disabled"},
                    "max_tokens": self.config.max_output_tokens,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._parse_message(self._request(request))

    @staticmethod
    def _parse_message(payload: Any) -> Message:
        try:
            choice = payload["choices"][0]
            if choice.get("finish_reason") in {
                "length",
                "content_filter",
                "insufficient_system_resource",
                "aborted",
            }:
                raise RuntimeError("DeepSeek 回复被截断或中止，请缩短输入、调整输出上限后重试。")
            source = choice["message"]
            content = source.get("content")
            message: Message = {"role": "assistant", "content": content}
            if calls := source.get("tool_calls"):
                message["tool_calls"] = calls
            elif not isinstance(content, str) or not content.strip():
                raise ValueError
            return message
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise RuntimeError(
                "DeepSeek 返回了无法识别的消息格式，请检查模型和 API 地址。"
            ) from None

    @staticmethod
    def _status_message(status: int) -> str:
        if status in {401, 403}:
            return "DeepSeek 拒绝认证或访问，请检查 API Key 和权限。"
        if status == 402:
            return "DeepSeek 余额不足，请检查账户。"
        if status == 429:
            return "DeepSeek 限流，请稍后重试。"
        if status in {400, 404, 422}:
            return "DeepSeek 不接受此请求，请检查模型名称、API 根地址及工具调用支持情况。"
        return f"DeepSeek 请求失败（HTTP {status}），请稍后重试。"
