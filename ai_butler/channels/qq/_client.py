import json
import logging
import time
from http.client import HTTPException
from threading import Lock
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ...config import Config, config

logger = logging.getLogger(__name__)


class QQClient:
    """QQ 渠道内部的 HTTP 实现，由 QQChannel 创建，不供业务层调用。"""

    def __init__(self, settings: Config = config):
        self.config = settings
        self._token = ""
        self._expires_at = 0.0
        self._token_lock = Lock()

    def access_token(self) -> str:
        with self._token_lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            data = self.request(
                "POST",
                "/app/getAppAccessToken",
                {
                    "appId": self.config.qq_app_id,
                    "clientSecret": self.config.qq_app_secret,
                },
                authenticated=False,
            )
            self._token = data["access_token"]
            self._expires_at = time.monotonic() + max(float(data["expires_in"]) - 60, 1)
            logger.info("qq_token_refreshed")
            return self._token

    def invalidate_token(self) -> None:
        with self._token_lock:
            self._token = ""

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        authenticated: bool = True,
        accepted_codes: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        attempt = 0
        while True:
            headers = {"Content-Type": "application/json"}
            if authenticated:
                headers["Authorization"] = "QQBot " + self.access_token()
            request = Request(
                self.config.qq_api_base_url.rstrip("/") + path,
                data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                headers=headers,
                method=method,
            )
            status = 200
            try:
                try:
                    with urlopen(request, timeout=self.config.timeout) as response:
                        raw = response.read()
                except HTTPError as error:
                    status = error.code
                    raw = error.read()
                    error.close()
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                code = data.get("code", 0)
                if code in accepted_codes:
                    return data
                if status == 401 and authenticated:
                    self.invalidate_token()
                elif status not in {429, 500, 502, 503, 504}:
                    if status >= 400 or code:
                        raise RuntimeError(
                            f"QQ 接口失败（HTTP {status}，code={code}），请检查凭据、权限和消息限制。"
                        )
                    if not data:
                        raise RuntimeError("QQ 接口未返回有效 JSON。")
                    return data
            except (OSError, HTTPException):
                status = 0
            if attempt == self.config.max_retries:
                raise RuntimeError(
                    f"QQ 请求失败或超时（HTTP {status}），请检查网络、凭据或稍后重试。"
                )
            logger.warning("qq_http_retry attempt=%d status=%d", attempt + 1, status)
            time.sleep(min(2**attempt, 8))
            attempt += 1

    def gateway_url(self) -> str:
        url = self.request("GET", "/gateway")["url"]
        if not url.startswith("wss://"):
            raise RuntimeError("QQ 网关没有返回安全的 WSS 地址。")
        return url

    def send_text(self, user_id: str, message_id: str, text: str) -> None:
        limit = self.config.qq_reply_max_chars
        if len(text) > limit:
            logger.info("reply_truncated channel=qq limit=%d", limit)
            notice = "\n（回复已截断，可继续提问。）"
            text = text[: max(limit - len(notice), 0)] + notice[:limit]
        self.request(
            "POST",
            f"/v2/users/{quote(user_id, safe='')}/messages",
            {
                "msg_type": 0,
                "content": text,
                "msg_id": message_id,
                "msg_seq": 1,
            },
            accepted_codes=(40054005,),
        )
