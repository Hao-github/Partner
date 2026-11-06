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
        match name:
            case "cli":
                return _CLIChannel
            case "qq":
                return _QQChannel
        raise ValueError(f"不支持的渠道：{name}")

    @staticmethod
    def inspect(name: str, *, discover: bool = False, settings: Config = config) -> None:
        ChannelService._channel_type(name).inspect(discover=discover, settings=settings)

    def run(self, handler: MessageHandler) -> None:
        if self._closed:
            return
        try:
            self._channel.receive(partial(self._process, handler=handler))
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._channel.close()

    def history(self, session_id: str) -> list[Message]:
        with self._store() as store:
            return store.load(session_id, self._settings.history_turns)

    def reply(self, incoming: IncomingMessage, text: str) -> bool:
        if self._closed or not self._channel.reply(incoming, text):
            return False
        logger.info(f"reply_sent channel={incoming.channel}")
        return True

    def _process(self, incoming: IncomingMessage, handler: MessageHandler) -> None:
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
