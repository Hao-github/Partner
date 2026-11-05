import json
import sqlite3
from dataclasses import replace

from ai_butler.models import IncomingMessage, ModelSelection, Reply
from ai_butler.storage import SessionStore
from tests.helpers import ProjectTest


class StorageTests(ProjectTest):
    def incoming(self):
        return IncomingMessage("test", "user", "test:a", "问题", "message")

    def result(self, text="回答"):
        return Reply(
            text, [{"role": "user", "content": "问题"}, {"role": "assistant", "content": text}]
        )

    def test_failed_cache_insert_rolls_back_conversation_turn(self):
        incoming = self.incoming()
        with SessionStore(self.settings.db_path) as store:
            first_model = ModelSelection("openai", "first-model")
            store.save(incoming, replace(self.result(), model=first_model))
            with self.assertRaises(sqlite3.IntegrityError):
                store.save(
                    incoming,
                    replace(
                        self.result("不应提交"), model=ModelSelection("deepseek", "second-model")
                    ),
                )
            self.assertEqual(store.load(incoming.session_id), self.result().messages)
            self.assertEqual(store.get_model(incoming.session_id), first_model)
            cached = store.get_delivery(incoming)
            self.assertEqual(cached and (cached.reply, cached.sent), ("回答", False))
        with SessionStore(self.settings.db_path) as reopened:
            self.assertEqual(reopened.load(incoming.session_id), self.result().messages)
            self.assertEqual(reopened.get_model(incoming.session_id), first_model)

    def test_existing_schema_and_delivery_keys_are_preserved(self):
        connection = sqlite3.connect(self.settings.db_path)
        connection.executescript("""
            CREATE TABLE turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                messages_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE deliveries (
                message_key TEXT PRIMARY KEY,
                reply TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0
            );
        """)
        connection.execute(
            "INSERT INTO turns(session_id, messages_json) VALUES (?, ?)",
            ("test:a", json.dumps(self.result().messages)),
        )
        connection.execute(
            "INSERT INTO deliveries(message_key, reply, sent) VALUES (?, ?, ?)",
            ("test:a:message", "回答", 1),
        )
        connection.commit()
        connection.close()
        with SessionStore(self.settings.db_path) as store:
            self.assertEqual(store.load("test:a"), self.result().messages)
            cached = store.get_delivery(self.incoming())
            self.assertEqual(cached and (cached.reply, cached.sent), ("回答", True))
