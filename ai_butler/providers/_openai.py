import json
from typing import Any
from urllib.request import Request

from ..models import Message
from ._base import Provider, _response_errors


class OpenAIProvider(Provider):
    """内部 OpenAI 适配：维护请求参数、认证、响应格式及错误提示。"""

    default_base_url = "https://api.openai.com/v1"

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
                    "max_completion_tokens": self.config.max_output_tokens,
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
    @_response_errors("OpenAI")
    def _parse_message(payload: Any) -> Message:
        choice = payload["choices"][0]
        if choice.get("finish_reason") in {"length", "content_filter"}:
            raise RuntimeError("OpenAI 回复被截断或中止，请缩短输入、调整输出上限后重试。")
        source = choice["message"]
        content = source.get("content")
        message: Message = {"role": "assistant", "content": content}
        if calls := source.get("tool_calls"):
            message["tool_calls"] = calls
        elif not isinstance(content, str) or not content.strip():
            raise ValueError
        return message

    @staticmethod
    def _status_message(status: int) -> str:
        if status in {401, 403}:
            return "OpenAI 拒绝认证或访问，请检查 API Key、权限及服务可用地区。"
        if status == 429:
            return "OpenAI 限流或额度不足，请稍后重试或检查账户额度。"
        if status in {400, 404, 422}:
            return "OpenAI 不接受此请求，请检查模型名称、API 根地址及工具调用支持情况。"
        return f"OpenAI 请求失败（HTTP {status}），请稍后重试。"
