import json
from concurrent.futures import Future
from contextlib import redirect_stdout
from dataclasses import replace
from http.client import HTTPMessage
from io import BytesIO, StringIO
from threading import Event, Thread, get_ident
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from ai_butler import Agent
from ai_butler.channels import _create_channel
from ai_butler.channels.qq._channel import QQChannel
from ai_butler.channels.qq._client import QQClient
from ai_butler.channels.qq._gateway import QQGateway
from ai_butler.models import IncomingMessage, Reply
from main import main
from tests.helpers import ProjectTest


def response(payload):
    return BytesIO(json.dumps(payload).encode())


class QQStartupTests(ProjectTest):
    def test_missing_qq_credentials_are_clear(self):
        output = StringIO()
        with patch("main.config", self.settings), redirect_stdout(output):
            self.assertEqual(main(["--channel", "qq"]), 2)
        self.assertIn("QQ_APP_ID", output.getvalue())

    def test_normal_mode_requires_allowlist(self):
        settings = replace(self.settings, qq_app_id="123", qq_app_secret="secret")
        with self.assertRaisesRegex(ValueError, "QQ_ALLOWED_USERS"):
            _create_channel("qq", settings=settings)

    @patch("ai_butler.channels.qq._channel._QQClient")
    def test_check_does_not_require_model_key_or_send_messages(self, client):
        settings = replace(self.settings, options={}, qq_app_id="123", qq_app_secret="secret")
        with redirect_stdout(StringIO()):
            Agent.inspect("qq", settings=settings)
        client.return_value.gateway_url.assert_called_once()
        client.return_value.send_text.assert_not_called()

    @patch("ai_butler.channels.qq._channel._QQGateway")
    @patch("ai_butler.channels.qq._channel._QQClient")
    def test_discovery_does_not_require_model_key(self, client, gateway):
        settings = replace(self.settings, options={}, qq_app_id="123", qq_app_secret="secret")
        with redirect_stdout(StringIO()):
            Agent.inspect("qq", discover=True, settings=settings)
        gateway.return_value.run.assert_called_once()
        gateway.return_value.close.assert_called_once()
        client.return_value.send_text.assert_not_called()


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
        with patch("ai_butler.channels.qq._channel._QQClient", return_value=self.client):
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
        with patch("ai_butler.channels.qq._channel._QQClient", return_value=self.client):
            restarted = _create_channel("qq", settings=self.qq_settings)
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

    @patch("ai_butler.channels.qq._channel._QQGateway")
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
        with self.assertLogs("ai_butler.channels.qq._channel") as logs:
            channel._done(future)
        self.assertNotIn("private-secret", str(logs.output))


class QQClientTests(ProjectTest):
    def client(self, **changes):
        settings = replace(
            self.settings, qq_app_id="123", qq_app_secret="test-qq-secret", **changes
        )
        client = QQClient(settings)
        self.open = Mock()
        patcher = patch("ai_butler.channels.qq._client.urlopen", self.open)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    @patch("ai_butler.channels.qq._client.time.monotonic")
    def test_token_is_cached_and_refreshed(self, clock):
        clock.return_value = 0
        client = self.client()
        self.open.side_effect = [
            response({"access_token": "first", "expires_in": "7200"}),
            response({"access_token": "second", "expires_in": "7200"}),
        ]
        self.assertEqual(client.access_token(), "first")
        self.assertEqual(client.access_token(), "first")
        self.assertEqual(self.open.call_count, 1)
        request = self.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.bot.qq.com/app/getAppAccessToken")
        self.assertEqual(
            json.loads(request.data), {"appId": "123", "clientSecret": "test-qq-secret"}
        )
        clock.return_value = 7200
        self.assertEqual(client.access_token(), "second")

    def test_private_reply_wire_format_and_local_length_limit(self):
        client = self.client(qq_reply_max_chars=30)
        self.open.side_effect = [
            response({"access_token": "token", "expires_in": 7200}),
            response({"id": "reply"}),
        ]
        client.send_text("user/id", "original-message", "很长的回答" * 20)
        request = self.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.bot.qq.com/v2/users/user%2Fid/messages")
        self.assertEqual(request.get_header("Authorization"), "QQBot token")
        self.assertEqual(
            (payload["msg_id"], payload["msg_seq"], payload["msg_type"]), ("original-message", 1, 0)
        )
        self.assertLessEqual(len(payload["content"]), 30)
        self.assertIn("已截断", payload["content"])

    def test_http_200_business_error_is_not_success_and_does_not_leak(self):
        client = self.client()
        self.open.return_value = response({"code": 100016, "message": "test-qq-secret"})
        with self.assertRaisesRegex(RuntimeError, "100016") as error:
            client.access_token()
        self.assertNotIn("test-qq-secret", str(error.exception))

    @patch("ai_butler.channels.qq._client.time.sleep")
    def test_401_refreshes_token_then_retries(self, sleep):
        client = self.client()
        self.open.side_effect = [
            response({"access_token": "first", "expires_in": 7200}),
            HTTPError("https://test.invalid", 401, "secret", HTTPMessage(), response({"code": 1})),
            response({"access_token": "second", "expires_in": 7200}),
            response({"url": "wss://api.bot.qq.com/websocket"}),
        ]
        self.assertTrue(client.gateway_url().startswith("wss://"))
        self.assertEqual(self.open.call_args.args[0].get_header("Authorization"), "QQBot second")
        self.assertEqual(self.open.call_count, 4)

    def test_duplicate_passive_reply_is_accepted(self):
        client = self.client()
        self.open.side_effect = [
            response({"access_token": "token", "expires_in": 7200}),
            HTTPError(
                "https://test.invalid",
                400,
                "duplicate",
                HTTPMessage(),
                response({"code": 40054005}),
            ),
        ]
        client.send_text("user", "message", "reply")

    @patch("ai_butler.channels.qq._client.time.sleep")
    def test_network_retries_are_bounded(self, sleep):
        for retries in (0, 1, 2):
            with self.subTest(retries=retries):
                client = self.client(max_retries=retries)
                self.open.side_effect = TimeoutError("secret")
                with self.assertRaises(RuntimeError) as error:
                    client.access_token()
                self.assertEqual(self.open.call_count, retries + 1)
                self.assertNotIn("secret", str(error.exception))

    def test_insecure_gateway_is_rejected(self):
        client = self.client()
        with (
            patch.object(client, "request", return_value={"url": "ws://example.com"}),
            self.assertRaisesRegex(RuntimeError, "WSS"),
        ):
            client.gateway_url()


class QQGatewayTests(ProjectTest):
    def gateway(self):
        self.client = Mock()
        self.client.config = self.settings
        self.client.access_token.return_value = "token"
        self.client.gateway_url.return_value = "wss://api.bot.qq.com/websocket"
        self.on_message = Mock()
        return QQGateway(self.client, self.on_message)

    def test_identify_and_resume_use_c2c_intent(self):
        gateway = self.gateway()
        self.assertEqual(
            gateway.identify(),
            {"op": 2, "d": {"token": "QQBot token", "intents": 1 << 25, "shard": [0, 1]}},
        )
        gateway.session_id, gateway.sequence = "session", 8
        self.assertEqual(
            gateway.identify()["d"], {"token": "QQBot token", "session_id": "session", "seq": 8}
        )

    def test_only_private_events_are_forwarded(self):
        gateway = self.gateway()
        with redirect_stdout(StringIO()):
            gateway.dispatch({"s": 1, "t": "READY", "d": {"session_id": "session"}})
        gateway.dispatch({"s": 2, "t": "GROUP_AT_MESSAGE_CREATE", "d": {"id": "group"}})
        gateway.dispatch({"s": 3, "t": "C2C_MESSAGE_CREATE", "d": {"id": "private"}})
        self.on_message.assert_called_once_with({"id": "private"})
        self.assertEqual((gateway.session_id, gateway.sequence), ("session", 3))

    def test_protocol_login_and_server_requested_heartbeat(self):
        gateway = self.gateway()
        socket = Mock()
        socket.recv.side_effect = [
            json.dumps({"op": 10, "d": {"heartbeat_interval": 45000}}),
            json.dumps({"op": 0, "s": 4, "t": "READY", "d": {"session_id": "session"}}),
            json.dumps({"op": 1}),
            json.dumps({"op": 11}),
            KeyboardInterrupt(),
        ]
        with redirect_stdout(StringIO()), self.assertRaises(KeyboardInterrupt):
            gateway.serve(socket)
        packets = [json.loads(call.args[0]) for call in socket.send.call_args_list]
        self.assertEqual(packets[0]["op"], 2)
        self.assertEqual(packets[1], {"op": 1, "d": 4})

    def test_missing_heartbeat_ack_triggers_reconnect(self):
        gateway = self.gateway()
        socket = Mock()
        clock = [0.0]
        reads = [0]

        def recv(timeout):
            reads[0] += 1
            if reads[0] == 1:
                return json.dumps({"op": 10, "d": {"heartbeat_interval": 1000}})
            clock[0] += timeout
            raise TimeoutError

        socket.recv.side_effect = recv
        with (
            patch("ai_butler.channels.qq._gateway.time.monotonic", side_effect=lambda: clock[0]),
            self.assertRaisesRegex(ConnectionError, "心跳"),
        ):
            gateway.serve(socket)
        self.assertEqual(
            [json.loads(call.args[0])["op"] for call in socket.send.call_args_list], [2, 1]
        )

    def test_logged_in_connection_outlives_login_deadline(self):
        gateway = self.gateway()
        self.client.config = replace(self.settings, timeout=1)
        clock = Mock(return_value=0.0)

        def advance_clock(data):
            clock.return_value = 2.0

        self.on_message.side_effect = advance_clock
        socket = Mock()
        socket.recv.side_effect = [
            json.dumps({"op": 10, "d": {"heartbeat_interval": 45000}}),
            json.dumps({"op": 0, "s": 4, "t": "READY", "d": {"session_id": "session"}}),
            json.dumps({"op": 0, "s": 5, "t": "C2C_MESSAGE_CREATE", "d": {"id": "message"}}),
            json.dumps({"op": 1}),
            KeyboardInterrupt(),
        ]
        with (
            patch("ai_butler.channels.qq._gateway.time.monotonic", clock),
            redirect_stdout(StringIO()),
            self.assertRaises(KeyboardInterrupt),
        ):
            gateway.serve(socket)
        self.on_message.assert_called_once_with({"id": "message"})
        self.assertEqual(json.loads(socket.send.call_args.args[0]), {"op": 1, "d": 5})

    def test_invalid_resume_resets_session(self):
        gateway = self.gateway()
        gateway.session_id, gateway.sequence = "old", 3
        socket = Mock()
        socket.recv.side_effect = [
            json.dumps({"op": 10, "d": {"heartbeat_interval": 45000}}),
            json.dumps({"op": 9, "d": False}),
        ]
        with self.assertRaises(ConnectionError):
            gateway.serve(socket)
        self.assertEqual((gateway.session_id, gateway.sequence), ("", None))

    @patch("ai_butler.channels.qq._gateway.connect")
    def test_permission_close_is_fatal(self, connect):
        gateway = self.gateway()
        failure = ConnectionClosedError(Close(4014, "private-secret"), Close(4014, ""), True)
        with (
            patch.object(gateway, "serve", side_effect=failure),
            self.assertRaisesRegex(RuntimeError, "4014") as error,
        ):
            gateway.run()
        self.assertNotIn("private-secret", str(error.exception))

    @patch("ai_butler.channels.qq._gateway.connect")
    def test_close_releases_socket_without_reconnecting(self, connect):
        gateway = self.gateway()
        socket = connect.return_value.__enter__.return_value

        def serve(connection):
            gateway.close()
            raise ConnectionClosedError(Close(1000, ""), Close(1000, ""), True)

        with patch.object(gateway, "serve", side_effect=serve):
            gateway.run()
        socket.close.assert_called_once()
        self.client.gateway_url.assert_called_once()
