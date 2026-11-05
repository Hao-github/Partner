import json
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from ai_butler.channels.qq._gateway import QQGateway
from tests.helpers import ProjectTest


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
