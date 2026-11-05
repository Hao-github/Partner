import json
import logging
import time
from abc import abstractmethod
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..config import Config, config
from ..models import Message
from .base import Provider

logger = logging.getLogger(__name__)


def parse_message(payload: Any) -> Message:
    """只接受文本及函数调用，过滤供应商额外元数据。"""
    try:
        choice = payload["choices"][0]
        if choice.get("finish_reason") in {
            "length",
            "content_filter",
            "insufficient_system_resource",
            "aborted",
        }:
            raise RuntimeError("模型回复被截断或中止，请缩短输入、调整输出上限后重试。")
        source = choice["message"]
        content = source.get("content")
        message: Message = {"role": "assistant", "content": content}
        calls = source.get("tool_calls") or []
        if calls:
            message["tool_calls"] = calls
        elif not isinstance(content, str) or not content.strip():
            raise ValueError
        return message
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise RuntimeError("模型返回了无法识别的消息格式，请检查模型和 API 地址。") from None


def status_message(status: int) -> str:
    if status in {401, 403}:
        return "模型服务拒绝认证或访问，请检查 API Key、权限及服务可用地区。"
    if status == 402:
        return "模型服务余额不足，请检查账户。"
    if status == 429:
        return "模型服务限流或额度不足，请稍后重试或检查账户额度。"
    if status in {400, 404, 422}:
        return "模型请求不被接受，请检查模型名称、API 根地址及工具调用支持情况。"
    return f"模型服务请求失败（HTTP {status}），请稍后重试。"


class ChatCompletionsProvider(Provider):
    """共用的 Chat Completions 传输层，屏蔽 HTTP、鉴权、重试及响应解析。"""

    def __init__(self, settings: Config = config):
        self.config = settings

    @abstractmethod
    def _options(self) -> dict[str, Any]:
        """由具体供应商提供协议参数。"""

    def _request(self, messages: list[Message], tools: list[dict[str, Any]]) -> Request:
        """只在协议边界转换参数；不让供应商字段进入 Agent。"""
        config = self.config
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": False,
        }
        payload.update(self._options())
        return Request(
            config.base_url + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        request = self._request(messages, tools)
        config = self.config
        started = time.monotonic()
        logger.debug("model_request_started provider=%s", config.provider)
        attempt = 0
        while True:
            try:
                with urlopen(request, timeout=config.timeout) as response:
                    raw = response.read()
                message = parse_message(json.loads(raw))
                logger.info(
                    "model_request_completed provider=%s duration_ms=%d tool_calls=%d",
                    config.provider,
                    (time.monotonic() - started) * 1000,
                    len(message.get("tool_calls", [])),
                )
                return message
            except HTTPError as error:
                status = error.code
                error.close()
                if (status != 429 and not 500 <= status <= 599) or attempt == config.max_retries:
                    logger.error(
                        "model_request_failed provider=%s status=%d", config.provider, status
                    )
                    raise RuntimeError(status_message(status)) from None
                reason = f"HTTP {status}"
            except (OSError, HTTPException):
                if attempt == config.max_retries:
                    logger.error("model_request_failed provider=%s reason=network", config.provider)
                    raise RuntimeError(
                        "连接模型服务失败或超时，请检查网络与 API 地址后重试。"
                    ) from None
                reason = "network_or_timeout"
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error("model_request_failed provider=%s reason=json", config.provider)
                raise RuntimeError("模型服务未返回有效 JSON，请检查 API 根地址。") from None
            except RuntimeError:
                logger.error("model_request_failed provider=%s reason=response", config.provider)
                raise
            # 不记录 URL、请求正文、会话、密钥或供应商错误正文。
            logger.warning(
                "model_retry provider=%s attempt=%d reason=%s", config.provider, attempt + 1, reason
            )
            time.sleep(min(2**attempt, 8))
            attempt += 1


class OpenAIProvider(ChatCompletionsProvider):
    """OpenAI 参数适配；共用传输层完成请求。"""

    def _options(self) -> dict[str, Any]:
        return {"max_completion_tokens": self.config.max_output_tokens}


class DeepSeekProvider(ChatCompletionsProvider):
    """DeepSeek 参数适配，关闭思考模式以使用现有工具调用流程。"""

    def _options(self) -> dict[str, Any]:
        return {"thinking": {"type": "disabled"}, "max_tokens": self.config.max_output_tokens}
