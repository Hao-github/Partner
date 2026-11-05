import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace
from threading import Event

from ..config import Config, config
from ..models import IncomingMessage, Message, Reply
from ..storage import SessionStore

MessageHandler = Callable[[IncomingMessage, list[Message]], Reply]
logger = logging.getLogger(__name__)


class Channel(ABC):
    """统一管理会话、去重、保存和交付；子类只实现平台收发与资源清理。

    业务回调接收统一消息与历史，返回 Reply。数据库只在当前处理线程打开，
    模型和渠道实现都不接触连接或存储细节。
    """

    def __init__(self, settings: Config = config):
        self._settings = settings
        self._stopping = Event()

    def receive(self, handler: MessageHandler) -> None:
        """阻塞接收统一消息，调用业务回调并自动回复。"""
        if not self._stopping.is_set():
            self._receive(handler)

    def reply(self, incoming: IncomingMessage, text: str) -> None:
        """回复已有消息，平台的路由和发送参数由实现处理。"""
        if not self._stopping.is_set():
            self._send(incoming, text)
            if not self._stopping.is_set():
                logger.info("reply_sent channel=%s", incoming.channel)

    def history(self, session_id: str) -> list[Message]:
        """读取渠道会话的最近完整轮次，不暴露数据库连接。"""
        with self._store() as store:
            return store.load(session_id, self._settings.history_turns)

    def close(self) -> None:
        """停止接收并释放资源，可重复调用。"""
        self._stopping.set()
        self._close()

    def _process(self, incoming: IncomingMessage, handler: MessageHandler) -> None:
        if self._stopping.is_set():
            return
        with self._store() as store:
            cached = store.get_delivery(incoming)
            if cached and cached.sent:
                logger.info("reply_skipped channel=%s reason=already_sent", incoming.channel)
                return
            if cached:
                logger.info("reply_reused channel=%s", incoming.channel)
                text = cached.reply
            else:
                logger.info("message_received channel=%s", incoming.channel)
                incoming = replace(incoming, model=store.get_model(incoming.session_id))
                history = store.load(incoming.session_id, self._settings.history_turns)
                try:
                    result = handler(incoming, history)
                except RuntimeError as error:
                    logger.warning("handler_failed channel=%s", incoming.channel)
                    result = Reply(self._failure_reply(error))
                store.save(incoming, result)
                text = result.text
                logger.info("reply_saved channel=%s", incoming.channel)
            self.reply(incoming, text)
            if not self._stopping.is_set():
                store.mark_sent(incoming)

    @contextmanager
    def _store(self) -> Generator[SessionStore, None, None]:
        """集中管理连接与存储错误，具体渠道不需要了解 SQLite 或 JSON。"""
        try:
            with SessionStore(self._settings.db_path) as store:
                yield store
        except (sqlite3.Error, OSError, json.JSONDecodeError):
            logger.error("storage_failed")
            raise RuntimeError(
                "本地会话存取失败，请检查数据库、目录权限及磁盘空间。此轮可能未保存。"
            ) from None

    def _failure_reply(self, error: RuntimeError) -> str:
        """默认让调用方呈现错误；平台可改为向用户回复统一提示。"""
        raise error

    @abstractmethod
    def _receive(self, handler: MessageHandler) -> None:
        """接收平台消息，串行交给 _process。"""

    @abstractmethod
    def _send(self, incoming: IncomingMessage, text: str) -> None:
        """发送文本；具体协议、原消息关联和限速留在子类。"""

    def _close(self) -> None:
        """子类有连接或工作线程时，在此释放。"""
        return
