import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.client import HTTPException
from typing import Any, ClassVar
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..config import Config, config
from ..models import Message

logger = logging.getLogger(__name__)


@contextmanager
def _response_errors(provider: str) -> Generator[None, None, None]:
    """可作解析器装饰器；仅转换格式错误，保留供应商明确的失败提示。"""
    try:
        yield
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise RuntimeError(
            f"{provider} 返回了无法识别的消息格式，请检查模型和 API 地址。"
        ) from None


@dataclass(frozen=True)
class ModelConfig:
    """单个模型客户端的完整只读配置，不携带渠道、存储或其他供应商选项。"""

    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    timeout: float
    max_retries: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        """在模型配置创建时校验凭据、模型与地址，之后不再补写字段。"""
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        if not self.api_key.strip():
            raise ValueError(f"请在项目 .env 中填写 {self.provider.upper()}_API_KEY。")
        if not self.api_key.isascii() or any(char.isspace() for char in self.api_key):
            raise ValueError("API Key 不能包含非 ASCII 字符或空白。")
        if not self.model.strip():
            raise ValueError("请在 .env 中设置 BUTLER_MODEL。")
        if not self.base_url.startswith("https://"):
            raise ValueError("BUTLER_BASE_URL 必须使用 HTTPS。")


class Provider(ABC):
    """内部模型端口；共用 HTTP 传输，具体协议由各供应商实现。"""

    name: ClassVar[str]
    default_model: ClassVar[str] = ""
    default_base_url: ClassVar[str] = ""

    def __init__(self, settings: Config = config, *, model: str | None = None):
        """仅在创建客户端时解析本供应商配置；启动覆盖不串用到其他供应商。"""
        same_provider = self.name == settings.provider
        prefix = self.name.upper()
        self.config = ModelConfig(
            provider=self.name,
            model=(model if model is not None else (settings.model if same_provider else ""))
            or settings.options.get(f"{prefix}_MODEL", self.default_model),
            base_url=(settings.base_url if same_provider else "")
            or settings.options.get(f"{prefix}_BASE_URL", self.default_base_url),
            api_key=settings.options.get(f"{prefix}_API_KEY", ""),
            timeout=settings.timeout,
            max_retries=settings.max_retries,
            max_output_tokens=settings.max_output_tokens,
        )

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
        logger.debug(f"model_request_started provider={config.provider}")
        for attempt in range(config.max_retries + 1):
            try:
                with urlopen(request, timeout=config.timeout) as response:
                    payload = json.loads(response.read())
                logger.info(
                    f"model_http_completed provider={config.provider} "
                    f"duration_ms={int((time.monotonic() - started) * 1000)}"
                )
                return payload
            except HTTPError as error:
                status = error.code
                error.close()
                if (status != 429 and not 500 <= status <= 599) or attempt == config.max_retries:
                    logger.error(f"model_request_failed provider={config.provider} status={status}")
                    raise RuntimeError(self._status_message(status)) from None
                reason = f"HTTP {status}"
            except (OSError, HTTPException):
                if attempt == config.max_retries:
                    logger.error(f"model_request_failed provider={config.provider} reason=network")
                    raise RuntimeError(
                        "连接模型服务失败或超时，请检查网络与 API 地址后重试。"
                    ) from None
                reason = "network_or_timeout"
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error(f"model_request_failed provider={config.provider} reason=json")
                raise RuntimeError("模型服务未返回有效 JSON，请检查 API 根地址。") from None
            logger.warning(
                f"model_retry provider={config.provider} attempt={attempt + 1} reason={reason}"
            )
            time.sleep(min(2**attempt, 8))
