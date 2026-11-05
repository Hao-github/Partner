import json
from dataclasses import replace
from http.client import HTTPMessage
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from ai_butler.channels.qq._client import QQClient
from tests.helpers import ProjectTest


def response(payload):
    return BytesIO(json.dumps(payload).encode())


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
        client = self.client(max_retries=1)
        self.open.side_effect = TimeoutError("secret")
        with self.assertRaises(RuntimeError) as error:
            client.access_token()
        self.assertEqual(self.open.call_count, 2)
        self.assertNotIn("secret", str(error.exception))

    def test_insecure_gateway_is_rejected(self):
        client = self.client()
        with (
            patch.object(client, "request", return_value={"url": "ws://example.com"}),
            self.assertRaisesRegex(RuntimeError, "WSS"),
        ):
            client.gateway_url()
