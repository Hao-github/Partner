import json
import sqlite3
from pathlib import Path
from typing import Self

from ..config import config
from ..models import Delivery, IncomingMessage, Message, ModelSelection, Reply


class SessionStore:
    """渠道共用的 SQLite 存储，一次事务保存轮次、会话模型与回复缓存。

    每次处理消息时在当前线程打开连接，离开 with 时关闭；不跨线程共享。
    沿用 turns、deliveries 表和消息键，保留已有会话与发送状态。
    """

    def __init__(self, path: Path = config.db_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, timeout=5)
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                messages_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, id);
            CREATE TABLE IF NOT EXISTS deliveries (
                message_key TEXT PRIMARY KEY,
                reply TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS session_models (
                session_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL
            );
        """)

    def load(self, session_id: str, limit: int = 20) -> list[Message]:
        rows = self._connection.execute(
            "SELECT messages_json FROM (SELECT id, messages_json FROM turns "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (session_id, limit),
        ).fetchall()
        return [message for (payload,) in rows for message in json.loads(payload)]

    def get_delivery(self, incoming: IncomingMessage) -> Delivery | None:
        if not incoming.message_id:
            return None
        row = self._connection.execute(
            "SELECT reply, sent FROM deliveries WHERE message_key = ?", (self._key(incoming),)
        ).fetchone()
        return Delivery(row[0], bool(row[1])) if row else None

    def get_model(self, session_id: str) -> ModelSelection | None:
        """读取会话的模型选择，未设置时交由应用使用启动默认值。"""
        row = self._connection.execute(
            "SELECT provider, model FROM session_models WHERE session_id = ?", (session_id,)
        ).fetchone()
        return ModelSelection(*row) if row else None

    def save(self, incoming: IncomingMessage, reply: Reply) -> None:
        """对话、模型选择与缓存同时提交；任何写入失败都回滚。"""
        with self._connection:
            if reply.messages:
                self._connection.execute(
                    "INSERT INTO turns(session_id, messages_json) VALUES (?, ?)",
                    (incoming.session_id, json.dumps(reply.messages, ensure_ascii=False)),
                )
            if reply.model is not None:
                self._connection.execute(
                    "INSERT INTO session_models(session_id, provider, model) VALUES (?, ?, ?) "
                    "ON CONFLICT(session_id) DO UPDATE SET "
                    "provider = excluded.provider, model = excluded.model",
                    (incoming.session_id, reply.model.provider, reply.model.model),
                )
            if incoming.message_id:
                self._connection.execute(
                    "INSERT INTO deliveries(message_key, reply) VALUES (?, ?)",
                    (self._key(incoming), reply.text),
                )

    def mark_sent(self, incoming: IncomingMessage) -> None:
        if not incoming.message_id:
            return
        with self._connection:
            self._connection.execute(
                "UPDATE deliveries SET sent = 1 WHERE message_key = ?", (self._key(incoming),)
            )

    @staticmethod
    def _key(incoming: IncomingMessage) -> str:
        return f"{incoming.session_id}:{incoming.message_id}"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()
