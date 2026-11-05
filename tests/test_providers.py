import json
from dataclasses import replace
from http.client import HTTPMessage, IncompleteRead
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from ai_butler.providers import _create_provider
from ai_butler.providers._deepseek import DeepSeekProvider
from ai_butler.providers._openai import OpenAIProvider
from ai_butler.tools.clock import TIME_TOOL
from tests.helpers import ProjectTest, completion, tool_call


class ProviderTests(ProjectTest):
    def client(self, **changes):
        settings = replace(self.settings, **changes)
        provider_type = DeepSeekProvider if settings.provider == "deepseek" else OpenAIProvider
        client = provider_type(settings)
        self.open = Mock()
        patcher = patch("ai_butler.providers._base.urlopen", self.open)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_factory_selects_provider_and_rejects_invalid_config(self):
        self.assertIsInstance(_create_provider(self.settings), DeepSeekProvider)
        settings = self.settings.select_model(provider="openai", model="test-model")
        self.assertIsInstance(
            _create_provider(replace(settings, options={"OPENAI_API_KEY": "test-key"})),
            OpenAIProvider,
        )
        with self.assertRaisesRegex(ValueError, "BUTLER_PROVIDER"):
            _create_provider(replace(self.settings, provider="unknown"))

    def response(self, text="你好"):
        return BytesIO(json.dumps(completion(text)).encode())

    def test_both_provider_requests(self):
        for name in ("deepseek", "openai"):
            with self.subTest(name=name):
                client = self.client(
                    provider=name,
                    model="test-model",
                    options={"DEEPSEEK_API_KEY": "test-secret", "OPENAI_API_KEY": "test-secret"},
                    base_url="https://test.invalid",
                )
                self.open.return_value = self.response()
                messages = [{"role": "user", "content": "你好"}]
                self.assertEqual(client.complete(messages, [TIME_TOOL])["content"], "你好")
                request = self.open.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(request.full_url, "https://test.invalid/chat/completions")
                self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
                self.assertEqual(payload["messages"], messages)
                self.assertEqual(payload["tools"], [TIME_TOOL])
                if name == "deepseek":
                    self.assertEqual(payload["thinking"], {"type": "disabled"})
                    self.assertIn("max_tokens", payload)
                    self.assertNotIn("max_completion_tokens", payload)
                else:
                    self.assertNotIn("thinking", payload)
                    self.assertIn("max_completion_tokens", payload)
                    self.assertNotIn("max_tokens", payload)

    @patch("ai_butler.providers._base.time.sleep")
    def test_transient_http_errors_retry_then_succeed(self, sleep):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                client = self.client()
                self.open.side_effect = [
                    HTTPError(
                        "https://test.invalid", status, "secret", HTTPMessage(), BytesIO(b"secret")
                    ),
                    self.response(),
                ]
                self.assertEqual(client.complete([], [TIME_TOOL])["content"], "你好")
                self.assertEqual(self.open.call_count, 2)

    @patch("ai_butler.providers._base.time.sleep")
    def test_network_retries_are_bounded_and_do_not_leak(self, sleep):
        client = self.client()
        self.open.side_effect = URLError("private-key")
        with (
            self.assertLogs("ai_butler.providers._base") as logs,
            self.assertRaises(RuntimeError) as error,
        ):
            client.complete([], [TIME_TOOL])
        self.assertEqual(self.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertNotIn("private-key", f"{error.exception}{logs.output}")

    def test_non_retryable_http_errors_fail_once(self):
        for name in ("deepseek", "openai"):
            for status in (400, 401, 402, 403, 404, 422):
                with self.subTest(name=name, status=status):
                    client = self.client(provider=name)
                    self.open.side_effect = HTTPError(
                        "https://test.invalid", status, "secret", HTTPMessage(), BytesIO(b"secret")
                    )
                    with self.assertRaises(RuntimeError) as error:
                        client.complete([], [TIME_TOOL])
                    self.assertEqual(self.open.call_count, 1)
                    self.assertIn(name, str(error.exception).lower())
                    self.assertNotIn("secret", str(error.exception))

    def test_timeout_interrupted_response_and_bad_json_are_friendly(self):
        for failure in (TimeoutError("private"), IncompleteRead(b"private")):
            with self.subTest(failure=failure):
                client = self.client(max_retries=0)
                self.open.side_effect = failure
                with self.assertRaises(RuntimeError) as error:
                    client.complete([], [TIME_TOOL])
                self.assertEqual(self.open.call_count, 1)
                self.assertNotIn("private", str(error.exception))
        client = self.client()
        self.open.return_value = BytesIO(b"<html>private</html>")
        with self.assertRaisesRegex(RuntimeError, "JSON"):
            client.complete([], [TIME_TOOL])

    def test_bad_completion_and_truncated_output(self):
        for name in ("deepseek", "openai"):
            for payload in (
                {},
                [],
                {"choices": []},
                completion(None),
                completion(""),
                completion("partial", finish="length"),
                completion("blocked", finish="content_filter"),
            ):
                with self.subTest(name=name, payload=payload):
                    client = self.client(provider=name)
                    self.open.return_value = BytesIO(json.dumps(payload).encode())
                    with self.assertRaises(RuntimeError):
                        client.complete([], [])

    def test_metadata_is_removed(self):
        for name in ("deepseek", "openai"):
            with self.subTest(name=name):
                client = self.client(provider=name)
                payload = completion()
                payload["choices"][0]["message"]["reasoning_content"] = "unused"
                self.open.return_value = BytesIO(json.dumps(payload).encode())
                self.assertEqual(client.complete([], []), {"role": "assistant", "content": "你好"})

    def test_tool_calls_without_text_are_preserved_by_both_providers(self):
        for name in ("deepseek", "openai"):
            with self.subTest(name=name):
                client = self.client(provider=name)
                calls = [tool_call("one"), tool_call("two")]
                self.open.return_value = BytesIO(
                    json.dumps(completion(None, calls=calls, finish="tool_calls")).encode()
                )
                self.assertEqual(
                    client.complete([], [TIME_TOOL]),
                    {"role": "assistant", "content": None, "tool_calls": calls},
                )

    def test_deepseek_interrupted_generation_is_rejected(self):
        for finish in ("insufficient_system_resource", "aborted"):
            with self.subTest(finish=finish):
                client = self.client()
                self.open.return_value = BytesIO(
                    json.dumps(completion("partial", finish=finish)).encode()
                )
                with self.assertRaisesRegex(RuntimeError, "DeepSeek.*中止"):
                    client.complete([], [])
