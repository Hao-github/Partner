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
        """共享只读配置，初始化令牌缓存及刷新锁，不立即发起请求。"""
        self.config = settings
        self._token = ""
        self._expires_at = 0.0
        self._token_lock = Lock()

    def access_token(self) -> str:
        """复用未过期的令牌，在锁内刷新并预留有效期余量。"""
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
        """清除失效令牌，使下次认证请求重新获取。"""
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
        """发送 QQ HTTP 请求，对认证失效和暂时错误做有限重试。"""
        status = 0
        for attempt in range(self.config.max_retries + 1):
            headers = {"Content-Type": "application/json"}
            if authenticated:
                headers["Authorization"] = f"QQBot {self.access_token()}"
            request = Request(
                f"{self.config.qq_api_base_url.rstrip('/')}{path}",
                data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                headers=headers,
                method=method,
            )
            try:
                try:
                    with urlopen(request, timeout=self.config.timeout) as response:
                        raw = response.read()
                    status = 200
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
            if attempt < self.config.max_retries:
                logger.warning(f"qq_http_retry attempt={attempt + 1} status={status}")
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"QQ 请求失败或超时（HTTP {status}），请检查网络、凭据或稍后重试。")

    def gateway_url(self) -> str:
        """获取并校验安全网关地址，供 WebSocket 建立连接。"""
        url = self.request("GET", "/gateway")["url"]
        if not url.startswith("wss://"):
            raise RuntimeError("QQ 网关没有返回安全的 WSS 地址。")
        return url

    def send_text(self, user_id: str, message_id: str, text: str) -> None:
        """按平台长度限制发送关联原消息的文本，接受重复投递状态码。"""
        limit = self.config.qq_reply_max_chars
        if len(text) > limit:
            logger.info(f"reply_truncated channel=qq limit={limit}")
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
