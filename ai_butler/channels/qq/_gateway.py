import json
import logging
import time
from collections.abc import Callable
from threading import Event

from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import ClientConnection, connect

from ._client import QQClient

logger = logging.getLogger(__name__)
PRIVATE_MESSAGE_INTENT = 1 << 25
FATAL_CLOSE_CODES = {4010, 4011, 4013, 4014, 4914, 4915}


class QQGateway:
    """QQ 渠道内部的 WebSocket 状态机：维护登录、心跳、重连和事件接收。"""

    def __init__(self, client: QQClient, on_message: Callable[[dict], None]):
        self.client = client
        self.on_message = on_message
        self.session_id = ""
        self.sequence: int | None = None
        self._stopping = Event()
        self._socket: ClientConnection | None = None

    def identify(self) -> dict:
        token = "QQBot " + self.client.access_token()
        if self.session_id:
            return {
                "op": 6,
                "d": {"token": token, "session_id": self.session_id, "seq": self.sequence},
            }
        return {"op": 2, "d": {"token": token, "intents": PRIVATE_MESSAGE_INTENT, "shard": [0, 1]}}

    def dispatch(self, payload: dict) -> None:
        self.sequence = payload["s"]
        event = payload.get("t")
        if event == "READY":
            self.session_id = payload["d"]["session_id"]
            logger.info("qq_gateway_ready")
            print("QQ 机器人已在线，等待私聊。", flush=True)
        elif event == "RESUMED":
            logger.info("qq_session_resumed")
        elif event == "C2C_MESSAGE_CREATE":
            self.on_message(payload["d"])

    def serve(self, socket: ClientConnection) -> None:
        hello = json.loads(socket.recv(timeout=self.client.config.timeout))
        if hello["op"] != 10:
            raise RuntimeError("QQ 网关没有返回 Hello 消息。")
        interval = hello["d"]["heartbeat_interval"] / 1000
        if interval <= 0:
            raise RuntimeError("QQ 网关心跳周期无效。")
        socket.send(json.dumps(self.identify()))
        heartbeat_at = time.monotonic() + interval
        login_deadline = time.monotonic() + self.client.config.timeout
        logged_in = False
        waiting_ack = False
        while not self._stopping.is_set():
            if not logged_in and time.monotonic() >= login_deadline:
                raise RuntimeError("QQ 网关登录超时，请检查应用和事件权限。")
            if time.monotonic() >= heartbeat_at:
                if waiting_ack:
                    raise ConnectionError("QQ 心跳确认超时。")
                socket.send(json.dumps({"op": 1, "d": self.sequence}))
                waiting_ack = True
                heartbeat_at = time.monotonic() + interval
            try:
                deadline = heartbeat_at if logged_in else min(heartbeat_at, login_deadline)
                payload = json.loads(socket.recv(timeout=max(deadline - time.monotonic(), 0)))
            except TimeoutError:
                continue
            opcode = payload["op"]
            if opcode == 0:
                self.dispatch(payload)
                if payload.get("t") in {"READY", "RESUMED"}:
                    logged_in = True
            elif opcode == 11:
                waiting_ack = False
            elif opcode == 1:
                socket.send(json.dumps({"op": 1, "d": self.sequence}))
                waiting_ack = True
                heartbeat_at = time.monotonic() + interval
            elif opcode in {7, 9}:
                if opcode == 9 and not payload.get("d"):
                    was_resuming = bool(self.session_id)
                    self.session_id, self.sequence = "", None
                    if not was_resuming:
                        raise RuntimeError("QQ 网关鉴权失败，请检查凭据与 C2C 事件权限。")
                raise ConnectionError("QQ 网关请求重新连接。")

    def run(self) -> None:
        delay = 1
        while not self._stopping.is_set():
            try:
                url = self.client.gateway_url()
                with connect(
                    url, open_timeout=self.client.config.timeout, ping_interval=None
                ) as socket:
                    self._socket = socket
                    if not self._stopping.is_set():
                        self.serve(socket)
            except ConnectionClosed as error:
                if self._stopping.is_set():
                    return
                code = error.rcvd.code if error.rcvd else None
                if code in FATAL_CLOSE_CODES:
                    raise RuntimeError(
                        f"QQ 网关拒绝连接（code={code}），请检查场景权限、应用状态和开发环境。"
                    ) from None
                if code in {4004, 4006, 4007}:
                    self.session_id, self.sequence = "", None
                if code == 4004:
                    self.client.invalidate_token()
                logger.warning("qq_disconnected code=%s", code)
            except (OSError, WebSocketException):
                logger.warning("qq_disconnected network_or_handshake")
            except (ValueError, KeyError, TypeError):
                raise RuntimeError("QQ 网关数据格式不正确，请检查平台协议或接入地址。") from None
            finally:
                self._socket = None
            if self._stopping.wait(delay):
                return
            delay = min(delay * 2, 30)

    def close(self) -> None:
        self._stopping.set()
        if self._socket is not None:
            self._socket.close()
