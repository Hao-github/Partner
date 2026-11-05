import json
import logging
import time
from abc import ABC, abstractmethod
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..config import Config, config
from ..models import Message

logger = logging.getLogger(__name__)


class Provider(ABC):
    """内部模型端口；共用 HTTP 传输，具体协议由各供应商实现。"""

    def __init__(self, settings: Config = config):
        self.config = settings

    @abstractmethod
    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        """生成一条统一模型消息；调用方不需要了解供应商协议。"""

    @staticmethod
    @abstractmethod
    def _status_message(status: int) -> str:
        """将供应商的 HTTP 状态转换为安全提示，不输出错误正文。"""

    def _request(self, request: Request) -> Any:
        """只负责 HTTP、JSON 解码和有限重试，不理解模型消息格式。"""
        config = self.config
        started = time.monotonic()
        logger.debug("model_request_started provider=%s", config.provider)
        attempt = 0
        while True:
            try:
                with urlopen(request, timeout=config.timeout) as response:
                    payload = json.loads(response.read())
                logger.info(
                    "model_http_completed provider=%s duration_ms=%d",
                    config.provider,
                    (time.monotonic() - started) * 1000,
                )
                return payload
            except HTTPError as error:
                status = error.code
                error.close()
                if (status != 429 and not 500 <= status <= 599) or attempt == config.max_retries:
                    logger.error(
                        "model_request_failed provider=%s status=%d", config.provider, status
                    )
                    raise RuntimeError(self._status_message(status)) from None
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
            logger.warning(
                "model_retry provider=%s attempt=%d reason=%s", config.provider, attempt + 1, reason
            )
            time.sleep(min(2**attempt, 8))
            attempt += 1
