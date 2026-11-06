import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from functools import partial

from ..config import Config, config
from ..models import IncomingMessage, Message, Reply
from ..storage import SessionStore
from ._base import Channel, MessageHandler
from .cli._channel import CLIChannel as _CLIChannel
from .qq._channel import QQChannel as _QQChannel

logger = logging.getLogger(__name__)


class ChannelService:
    """统一渠道装配、历史、去重、业务调用、持久化与回复交付。"""

    def __init__(self, name: str, *, session: str = "default", settings: Config = config):
        """按渠道类型装配传输实现，共享只读配置并延后打开会话存储。"""
        self._settings = settings
        self._closed = False
        channel_type = self._channel_type(name)
        self._channel = (
            _CLIChannel(session, settings, history=self.history)
            if channel_type is _CLIChannel
            else channel_type(settings)
        )

    @staticmethod
    def _channel_type(name: str) -> type[Channel]:
        """唯一的渠道类型选择入口；未知渠道在装配前报错。"""
        match name:
            case "cli":
                return _CLIChannel
            case "qq":
                return _QQChannel
        raise ValueError(f"不支持的渠道：{name}")

    @staticmethod
    def inspect(name: str, *, discover: bool = False, settings: Config = config) -> None:
        """执行独立渠道诊断，不创建正式渠道或模型。"""
        ChannelService._channel_type(name).inspect(discover=discover, settings=settings)

    def run(self, handler: MessageHandler) -> None:
        """接收平台消息并交给公共处理流程，退出时统一关闭渠道。"""
        if self._closed:
            return
        try:
            self._channel.receive(partial(self._process, handler=handler))
        finally:
            self.close()

    def close(self) -> None:
        """阻止新消息处理并关闭渠道，可重复调用。"""
        if self._closed:
            return
        self._closed = True
        self._channel.close()

    def history(self, session_id: str) -> list[Message]:
        """读取配置轮数内的完整会话历史，并及时关闭存储连接。"""
        with self._store() as store:
            return store.load(session_id, self._settings.history_turns)

    def reply(self, incoming: IncomingMessage, text: str) -> bool:
        """通过渠道投递文本，返回是否完成发送且渠道仍可用。"""
        if self._closed or not self._channel.reply(incoming, text):
            return False
        logger.info(f"reply_sent channel={incoming.channel}")
        return True

    def _process(self, incoming: IncomingMessage, handler: MessageHandler) -> None:
        """处理去重、历史与业务调用，先保存回复再发送和标记交付。"""
        if self._closed:
            return
        with self._store() as store:
            cached = store.get_delivery(incoming)
            if cached and cached.sent:
                logger.info(f"reply_skipped channel={incoming.channel} reason=already_sent")
                return
            if cached:
                logger.info(f"reply_reused channel={incoming.channel}")
                text = cached.reply
            else:
                logger.info(f"message_received channel={incoming.channel}")
                incoming = replace(incoming, model=store.get_model(incoming.session_id))
                history = store.load(incoming.session_id, self._settings.history_turns)
                try:
                    result = handler(incoming, history)
                except RuntimeError as error:
                    logger.warning(f"handler_failed channel={incoming.channel}")
                    result = Reply(self._channel.failure_reply(error))
                store.save(incoming, result)
                text = result.text
                logger.info(f"reply_saved channel={incoming.channel}")
            if self.reply(incoming, text) and not self._closed:
                store.mark_sent(incoming)

    @contextmanager
    def _store(self) -> Generator[SessionStore, None, None]:
        """数据库仅在处理线程打开，统一转换存储错误。"""
        try:
            with SessionStore(self._settings.db_path) as store:
                yield store
        except (sqlite3.Error, OSError, json.JSONDecodeError):
            logger.error("storage_failed")
            raise RuntimeError(
                "本地会话存取失败，请检查数据库、目录权限及磁盘空间。此轮可能未保存。"
            ) from None
