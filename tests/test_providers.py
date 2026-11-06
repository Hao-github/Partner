import json
from dataclasses import replace
from http.client import HTTPMessage, IncompleteRead
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from ai_butler.models import ModelSelection
from ai_butler.providers import ModelService
from ai_butler.providers._deepseek import DeepSeekProvider
from ai_butler.providers._openai import OpenAIProvider
from tests.helpers import VERSION_TOOL, ProjectTest, completion, tool_call


class ModelServiceTests(ProjectTest):
    def test_model_clients_are_reused_and_services_keep_separate_caches(self):
        with patch.object(
            ModelService, "_create_provider", wraps=ModelService._create_provider
        ) as factory:
            first = ModelService(settings=self.settings)
            default = first.default_model
            alternate = ModelSelection("deepseek", "alternate")
            first.prepare(default)
            first.prepare(alternate)
            first.prepare(alternate)
            self.assertEqual(factory.call_count, 2)
            with patch.object(
                DeepSeekProvider,
                "complete",
                autospec=True,
                return_value={"role": "assistant", "content": "ok"},
            ) as complete:
                first.complete(alternate, [], [])
                client = complete.call_args.args[0]
                self.assertEqual(client.config.model, "alternate")
                first.complete(alternate, [], [])
                self.assertIs(complete.call_args.args[0], client)
                self.assertEqual(factory.call_count, 2)
                first.complete(default, [], [])
                default_client = complete.call_args.args[0]
                second = ModelService(settings=self.settings)
                second.complete(default, [], [])
                self.assertIsNot(complete.call_args.args[0], default_client)
            self.assertEqual(first.default_model, default)
            self.assertEqual(self.settings.model, "deepseek-flash")

    def test_failed_preparation_does_not_cache_client_or_bypass_later_validation(self):
        service = ModelService(settings=self.settings)
        selection = ModelSelection("openai", "saved-model")
        with patch.object(
            ModelService, "_create_provider", wraps=ModelService._create_provider
        ) as factory:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                    service.complete(selection, [], [])
            self.assertEqual(factory.call_count, 2)


class ProviderTests(ProjectTest):
    def client(self, **changes):
        changes.setdefault("options", {**self.settings.options, "OPENAI_API_KEY": "test-openai"})
        settings = replace(self.settings, **changes)
        provider_type = DeepSeekProvider if settings.provider == "deepseek" else OpenAIProvider
        client = provider_type(settings)
        self.open = Mock()
        patcher = patch("ai_butler.providers._base.urlopen", self.open)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_factory_selects_provider_and_rejects_invalid_config(self):
        self.assertIsInstance(ModelService._create_provider(self.settings), DeepSeekProvider)
        self.assertIsInstance(
            ModelService._create_provider(
                replace(self.settings, options={"OPENAI_API_KEY": "test-key"}),
                provider="openai",
                model="test-model",
            ),
            OpenAIProvider,
        )
        with self.assertRaisesRegex(ValueError, "BUTLER_PROVIDER"):
            ModelService._create_provider(replace(self.settings, provider="unknown"))

    def test_provider_defaults_and_overrides_are_resolved_during_initialization(self):
        settings = replace(
            self.settings,
            model="",
            base_url="",
            options={
                **self.settings.options,
                "DEEPSEEK_MODEL": "configured-model",
                "DEEPSEEK_BASE_URL": "https://custom.invalid/",
            },
        )
        configured = DeepSeekProvider(settings).config
        self.assertEqual(configured.model, "configured-model")
        self.assertEqual(configured.base_url, "https://custom.invalid")
        explicit = DeepSeekProvider(
            replace(settings, model="startup-model", base_url="https://startup.invalid"),
            model="session-model",
        ).config
        self.assertEqual(explicit.model, "session-model")
        self.assertEqual(explicit.base_url, "https://startup.invalid")
        self.assertEqual(settings.model, "")
        self.assertEqual(settings.base_url, "")

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
                self.assertEqual(client.complete(messages, [VERSION_TOOL])["content"], "你好")
                request = self.open.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(request.full_url, "https://test.invalid/chat/completions")
                self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
                self.assertEqual(payload["messages"], messages)
                self.assertEqual(payload["tools"], [VERSION_TOOL])
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
                self.assertEqual(client.complete([], [VERSION_TOOL])["content"], "你好")
                self.assertEqual(self.open.call_count, 2)

    @patch("ai_butler.providers._base.time.sleep")
    def test_network_retries_are_bounded_and_do_not_leak(self, sleep):
        client = self.client()
        self.open.side_effect = URLError("private-key")
        with (
            self.assertLogs("ai_butler.providers._base") as logs,
            self.assertRaises(RuntimeError) as error,
        ):
            client.complete([], [VERSION_TOOL])
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
                        client.complete([], [VERSION_TOOL])
                    self.assertEqual(self.open.call_count, 1)
                    self.assertIn(name, str(error.exception).lower())
                    self.assertNotIn("secret", str(error.exception))

    def test_timeout_interrupted_response_and_bad_json_are_friendly(self):
        for failure in (TimeoutError("private"), IncompleteRead(b"private")):
            with self.subTest(failure=failure):
                client = self.client(max_retries=0)
                self.open.side_effect = failure
                with self.assertRaises(RuntimeError) as error:
                    client.complete([], [VERSION_TOOL])
                self.assertEqual(self.open.call_count, 1)
                self.assertNotIn("private", str(error.exception))
        client = self.client()
        self.open.return_value = BytesIO(b"<html>private</html>")
        with self.assertRaisesRegex(RuntimeError, "JSON"):
            client.complete([], [VERSION_TOOL])

    def test_response_format_errors_are_safe_and_not_retried(self):
        for name in ("deepseek", "openai"):
            client = self.client(provider=name)
            for payload in (
                {"private": "private-key"},
                [],
                {"choices": []},
                {"choices": [None]},
                completion(None),
                completion(""),
            ):
                with self.subTest(name=name, payload=payload):
                    self.open.reset_mock()
                    self.open.return_value = BytesIO(json.dumps(payload).encode())
                    with self.assertRaisesRegex(RuntimeError, "无法识别的消息格式") as error:
                        client.complete([], [])
                    self.assertIn(name, str(error.exception).lower())
                    self.assertNotIn("private-key", str(error.exception))
                    self.assertIsNone(error.exception.__cause__)
                    self.assertEqual(self.open.call_count, 1)
            self.open.return_value = self.response()
            self.assertEqual(client.complete([], []), {"role": "assistant", "content": "你好"})

    def test_truncated_output_keeps_provider_error_without_retry(self):
        for name in ("deepseek", "openai"):
            for finish in ("length", "content_filter"):
                with self.subTest(name=name, finish=finish):
                    client = self.client(provider=name)
                    self.open.return_value = BytesIO(
                        json.dumps(completion("partial", finish=finish)).encode()
                    )
                    with self.assertRaisesRegex(RuntimeError, "截断或中止") as error:
                        client.complete([], [])
                    self.assertIn(name, str(error.exception).lower())
                    self.assertEqual(self.open.call_count, 1)

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
                    client.complete([], [VERSION_TOOL]),
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
