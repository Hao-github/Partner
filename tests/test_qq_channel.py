from concurrent.futures import Future
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from threading import Event, Thread, get_ident
from unittest.mock import Mock, patch

from ai_butler.channels import create_channel
from ai_butler.channels.qq import QQChannel
from ai_butler.models import IncomingMessage, Reply
from tests.helpers import ProjectTest


class QQChannelTests(ProjectTest):
    def channel(self):
        self.qq_settings = replace(
            self.settings,
            qq_app_id="123",
            qq_app_secret="test-secret",
            qq_allowed_users=("owner",),
            qq_min_interval=0,
        )
        self.client = Mock()
        with patch("ai_butler.channels.qq.channel._QQClient", return_value=self.client):
            channel = QQChannel(self.qq_settings)
        self.addCleanup(channel.close)
        return channel

    def incoming(self, user="owner", message="message"):
        return IncomingMessage("qq", user, f"qq:123:c2c:{user}", "你好", message)

    def test_replay_is_deduplicated_across_channel_restart(self):
        handler = Mock(return_value=Reply("模型回答"))
        channel = self.channel()
        channel._process(self.incoming(), handler)
        channel._process(self.incoming(), handler)
        self.client.send_text.assert_called_once_with("owner", "message", "模型回答")
        handler.assert_called_once_with(self.incoming(), [])
        with patch("ai_butler.channels.qq.channel._QQClient", return_value=self.client):
            restarted = create_channel("qq", settings=self.qq_settings)
        self.addCleanup(restarted.close)
        self.assertIsInstance(restarted, QQChannel)
        assert isinstance(restarted, QQChannel)
        restarted._process(self.incoming(), handler)
        self.assertEqual(self.client.send_text.call_count, 1)
        cached = self.store().get_delivery(self.incoming())
        self.assertEqual(cached and (cached.reply, cached.sent), ("模型回答", True))

    def test_pending_reply_reuses_handler_result_on_redelivery(self):
        handler = Mock(return_value=Reply("缓存回答"))
        channel = self.channel()
        self.client.send_text.side_effect = [RuntimeError("network"), None]
        with self.assertRaises(RuntimeError):
            channel._process(self.incoming(), handler)
        channel._process(self.incoming(), handler)
        handler.assert_called_once()
        self.assertEqual(self.client.send_text.call_count, 2)

    def test_non_allowlisted_and_non_text_messages_do_not_enter_worker(self):
        channel = self.channel()
        handler = Mock()
        with patch.object(channel._executor, "submit") as submit:
            for event in (
                {"id": "1", "author": {"user_openid": "stranger"}, "content": "你好"},
                {"id": "2", "author": {"user_openid": "owner"}, "content": ""},
                {
                    "id": "3",
                    "author": {"user_openid": "owner"},
                    "content": "图片",
                    "message_type": 3,
                },
            ):
                channel._accept(event, handler)
            submit.assert_not_called()
        handler.assert_not_called()

    @patch("ai_butler.channels.qq.channel._QQGateway")
    def test_receive_converts_events_and_runs_handler_off_gateway_thread(self, gateway):
        channel = self.channel()
        received = []
        thread_ids = []

        def handler(incoming, history):
            received.append(incoming)
            thread_ids.append(get_ident())
            return Reply("收到")

        def run():
            accept = gateway.call_args.args[1]
            accept({"id": "1", "author": {"user_openid": "owner"}, "content": " 第一条 "})
            accept({"id": "2", "author": {"user_openid": "owner"}, "content": "第二条"})
            channel._executor.submit(lambda: None).result(timeout=5)

        gateway.return_value.run.side_effect = run
        channel.receive(handler)
        self.assertEqual(
            received,
            [
                IncomingMessage("qq", "owner", "qq:123:c2c:owner", "第一条", "1"),
                IncomingMessage("qq", "owner", "qq:123:c2c:owner", "第二条", "2"),
            ],
        )
        self.assertEqual(self.client.send_text.call_count, 2)
        self.assertEqual(len(set(thread_ids)), 1)
        self.assertNotEqual(thread_ids[0], get_ident())
        channel.close()
        gateway.return_value.close.assert_called_once()

    def test_handler_failure_sends_simple_error_without_saving_turn(self):
        channel = self.channel()
        channel._process(self.incoming(), Mock(side_effect=RuntimeError("private-details")))
        reply = self.client.send_text.call_args.args[2]
        self.assertIn("重新提问", reply)
        self.assertNotIn("private", reply)
        self.assertEqual(self.store().load("qq:123:c2c:owner"), [])

    def test_reply_hides_platform_target_and_stops_after_close(self):
        channel = self.channel()
        channel.reply(self.incoming(), "直接回复")
        self.client.send_text.assert_called_once_with("owner", "message", "直接回复")
        channel.close()
        channel.reply(self.incoming(message="later"), "停止后不发送")
        self.assertEqual(self.client.send_text.call_count, 1)

    def test_close_cancels_queued_work_and_does_not_send_running_reply(self):
        channel = self.channel()
        started, release = Event(), Event()
        self.addCleanup(release.set)

        def respond(incoming, history):
            started.set()
            release.wait(5)
            return Reply("处理中关闭")

        handler = Mock(side_effect=respond)
        channel._accept(
            {"id": "1", "author": {"user_openid": "owner"}, "content": "第一条"}, handler
        )
        self.assertTrue(started.wait(5))
        channel._accept(
            {"id": "2", "author": {"user_openid": "owner"}, "content": "第二条"}, handler
        )
        closing = Thread(target=channel.close)
        closing.start()
        self.assertTrue(channel._stopping.wait(5))
        release.set()
        closing.join(5)
        self.assertFalse(closing.is_alive())
        handler.assert_called_once()
        self.client.send_text.assert_not_called()
        cached = self.store().get_delivery(self.incoming(message="1"))
        self.assertEqual(cached and (cached.reply, cached.sent), ("处理中关闭", False))

    def test_discovery_only_prints_openid(self):
        output = StringIO()
        with redirect_stdout(output):
            QQChannel._discover_user(
                {"author": {"user_openid": "owner"}, "content": "private-text"}
            )
        self.assertIn("QQ_ALLOWED_USERS=owner", output.getvalue())
        self.assertNotIn("private-text", output.getvalue())

    def test_worker_errors_do_not_log_private_exception_text(self):
        channel = self.channel()
        channel._slots.acquire()
        future = Future()
        future.set_exception(RuntimeError("private-secret"))
        with self.assertLogs("ai_butler.channels.qq.channel") as logs:
            channel._done(future)
        self.assertNotIn("private-secret", str(logs.output))
