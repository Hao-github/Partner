import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore

from ...config import Config, config
from ...models import IncomingMessage
from .._base import Channel, IncomingHandler
from ._client import QQClient as _QQClient
from ._gateway import QQGateway as _QQGateway

logger = logging.getLogger(__name__)


class QQChannel(Channel):
    """QQ 平台收发：白名单、事件转换、工作线程、限速和原消息回复。

    网关线程只提交任务，单个工作线程运行服务提供的消息回调。
    会话、缓存和去重均由 ChannelService 管理，不在这里操作存储。
    """

    def __init__(self, settings: Config = config):
        settings.validate_qq()
        super().__init__(settings)
        self._client = _QQClient(settings)
        # 首版个人私聊全局串行；模型推理不占用网关接收和心跳线程。
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qq-agent")
        self._slots = BoundedSemaphore(16)
        self._last_sent: dict[str, float] = {}
        self._gateway: _QQGateway | None = None

    @classmethod
    def inspect(cls, *, discover: bool = False, settings: Config = config) -> None:
        """独立检查连接或识别发送者，内部组装通信组件，不要求模型和白名单。"""
        settings.validate_qq(require_users=False)
        client = _QQClient(settings)
        if not discover:
            client.gateway_url()
            print("QQ 凭据验证成功，已获取网关地址。此检查不验证收发消息权限。")
            return
        print("识别模式：请用自己的 QQ 给机器人发送私聊。这里只显示 OpenID，不调用模型、不回复。")
        gateway = _QQGateway(client, cls._discover_user)
        try:
            gateway.run()
        finally:
            gateway.close()

    def _receive(self, handler: IncomingHandler) -> None:
        self._gateway = _QQGateway(self._client, lambda data: self._accept(data, handler))
        self._gateway.run()

    def _accept(self, data: dict, handler: IncomingHandler) -> None:
        user_id = data["author"]["user_openid"]
        text = data.get("content", "").strip()
        if user_id not in self._settings.qq_allowed_users or not text:
            logger.debug("message_ignored channel=qq reason=sender_or_empty")
            return
        if data.get("message_type", 0) != 0:
            logger.debug("message_ignored channel=qq reason=unsupported_type")
            return
        incoming = IncomingMessage(
            channel="qq",
            user_id=user_id,
            text=text,
            message_id=data["id"],
            session_id=f"qq:{self._settings.qq_app_id}:c2c:{user_id}",
        )
        if self._stopping.is_set() or not self._slots.acquire(blocking=False):
            logger.warning("qq_queue_full_or_stopping")
            return
        self._executor.submit(handler, incoming).add_done_callback(self._done)

    def _done(self, future: Future) -> None:
        self._slots.release()
        if not future.cancelled() and future.exception() is not None:
            # 不输出异常正文，防止第三方错误带回私聊内容或凭据。
            logger.error("qq_message_failed; 检查网络、平台权限及模型配置后重新提问")

    def failure_reply(self, error: RuntimeError) -> str:
        return "这次模型请求没有完成，请稍后重新提问。"

    def _send(self, incoming: IncomingMessage, text: str) -> None:
        """封装回复目标、原消息关联、限速和平台发送。"""
        delay = self._settings.qq_min_interval - (
            time.monotonic() - self._last_sent.get(incoming.user_id, 0)
        )
        if self._stopping.wait(max(delay, 0)):
            return
        self._client.send_text(incoming.user_id, incoming.message_id, text)
        self._last_sent[incoming.user_id] = time.monotonic()

    def _close(self) -> None:
        """先阻止新任务和发送，再关闭网关并取消排队任务。"""
        if self._gateway is not None:
            self._gateway.close()
        self._executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _discover_user(data: dict) -> None:
        """只在用户显式启动识别模式时输出 OpenID。"""
        user_id = data["author"]["user_openid"]
        print(
            f"收到私聊，发送者 OpenID：{user_id}\n确认是自己的账号后填写 QQ_ALLOWED_USERS={user_id}",
            flush=True,
        )
