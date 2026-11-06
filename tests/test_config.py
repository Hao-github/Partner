import json
import os
import shutil
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from operator import setitem
from pathlib import Path
from unittest.mock import patch

from ai_butler.config import Config, config
from ai_butler.core import agent as agent_module
from ai_butler.providers import ModelService
from ai_butler.providers import _base as provider_module
from tests.helpers import ProjectTest


class ConfigTests(ProjectTest):
    def test_fields_read_environment_with_correct_types(self):
        with patch.dict(
            os.environ,
            {
                "BUTLER_PROVIDER": "openai",
                "BUTLER_CONFIG_VERSION": "test-v2",
                "BUTLER_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
                "BUTLER_TIMEOUT_SECONDS": "12.5",
                "BUTLER_MAX_RETRIES": "1",
                "BUTLER_HISTORY_TURNS": "8",
            },
            clear=True,
        ):
            settings = Config()
        resolved = ModelService._create_provider(settings).config
        self.assertEqual(resolved.api_key, "test-key")
        self.assertEqual(settings.config_version, "test-v2")
        self.assertEqual(resolved.base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.timeout, 12.5)
        self.assertEqual(settings.max_retries, 1)
        self.assertEqual(settings.history_turns, 8)
        self.assertNotIn("test-key", f"{settings!r}{resolved!r}")

    def test_modules_share_the_same_config_instance(self):
        self.assertIs(provider_module.config, config)
        self.assertIs(agent_module.config, config)

    def test_dotenv_is_read_from_project_root_outside_working_directory(self):
        # 在临时包里导入真实 config.py，验证 .env 加载且不接触用户的密钥文件。
        package = self.root / "ai_butler"
        package.mkdir()
        (package / "__init__.py").touch()
        source = Path(__file__).resolve().parents[1] / "ai_butler" / "config.py"
        shutil.copyfile(source, package / "config.py")
        (self.root / ".env").write_text(
            'BUTLER_PROVIDER=openai\nBUTLER_MODEL="file-model"\nOPENAI_API_KEY=test-file-key\n'
            "BUTLER_BASE_URL=https://test.invalid\n"
            "BUTLER_TIMEOUT_SECONDS=9.5\nBUTLER_DB_PATH=data/test.sqlite3\n",
            encoding="utf-8-sig",
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("BUTLER_")
            and key not in {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "PYTHON_DOTENV_DISABLED"}
        }
        env.update(PYTHONPATH=str(self.root), BUTLER_MODEL="environment-model", PYTHONUTF8="1")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import json; from ai_butler.config import config; "
                    "print(json.dumps([config.model, config.timeout, str(config.db_path)]))"
                ),
            ],
            cwd=self.root.parent,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                "environment-model",
                9.5,
                str(self.root / "data" / "test.sqlite3"),
            ],
        )

    def test_missing_key_has_clear_message(self):
        with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
            ModelService(settings=replace(self.settings, options={}))

    def test_provider_initialization_uses_own_defaults_and_preserves_startup_config(self):
        settings = replace(
            self.settings, options={**self.settings.options, "OPENAI_API_KEY": "test-openai"}
        )
        selected = ModelService._create_provider(
            settings, provider=" OpenAI ", model="test-model"
        ).config
        self.assertEqual(selected.provider, "openai")
        self.assertEqual(selected.base_url, "https://api.openai.com/v1")
        self.assertEqual(selected.model, "test-model")
        self.assertEqual(self.settings.provider, "deepseek")
        self.assertEqual(self.settings.base_url, "https://api.deepseek.com")
        resolved = ModelService._create_provider(
            replace(settings, model="", base_url=""), provider="deepseek"
        ).config
        self.assertEqual(resolved.model, "deepseek-flash")
        self.assertEqual(resolved.base_url, "https://api.deepseek.com")

    def test_provider_initialization_keeps_same_provider_custom_endpoint(self):
        settings = replace(self.settings, base_url="https://test.invalid")
        selected = ModelService._create_provider(settings, model="custom-model").config
        self.assertEqual(selected.base_url, "https://test.invalid")
        self.assertEqual(selected.model, "custom-model")

    def test_openai_model_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "BUTLER_MODEL"):
            ModelService._create_provider(
                replace(
                    self.settings, provider="openai", model="", options={"OPENAI_API_KEY": "test"}
                )
            )

    def test_invalid_provider_and_runtime_limits_are_rejected(self):
        for changes in (
            {"config_version": " "},
            {"provider": "unknown"},
            {"timeout": float("nan")},
            {"timeout": 0},
            {"max_retries": -1},
            {"history_turns": 0},
            {"max_tool_rounds": 0},
            {"base_url": "http://example.com"},
            {"options": {"DEEPSEEK_API_KEY": "test\nheader"}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ModelService._create_provider(replace(self.settings, **changes))

    def test_options_snapshot_hides_credentials_and_copies_are_independent(self):
        with patch.dict(os.environ, {"FUTURE_API_KEY": "private-key", "FUTURE_LIMIT": "7"}):
            settings = Config(provider="future")
            os.environ["FUTURE_LIMIT"] = "8"
        self.assertEqual(settings.options["FUTURE_API_KEY"], "private-key")
        self.assertEqual(settings.options["FUTURE_LIMIT"], "7")
        self.assertNotIn("private-key", repr(settings))
        changed = replace(settings, options={**settings.options, "FUTURE_LIMIT": "9"})
        self.assertEqual(changed.options["FUTURE_LIMIT"], "9")
        self.assertEqual(settings.options["FUTURE_LIMIT"], "7")

    def test_startup_config_and_options_are_frozen_and_detached_from_input(self):
        options = {"FUTURE_LIMIT": "7"}
        settings = replace(self.settings, provider=" DeepSeek ", options=options)
        options["FUTURE_LIMIT"] = "8"
        self.assertEqual(settings.provider, "deepseek")
        self.assertEqual(settings.options["FUTURE_LIMIT"], "7")
        self.assertRaises(FrozenInstanceError, setattr, settings, "model", "changed")
        self.assertRaises(TypeError, setitem, settings.options, "FUTURE_LIMIT", "9")

    def test_model_config_is_complete_frozen_and_does_not_expose_startup_options(self):
        resolved = ModelService._create_provider(self.settings).config
        self.assertEqual(resolved.model, "deepseek-flash")
        self.assertEqual(resolved.api_key, "test-secret")
        self.assertNotIn("test-secret", repr(resolved))
        self.assertFalse(hasattr(resolved, "options"))
        self.assertFalse(hasattr(resolved, "qq_app_secret"))
        self.assertRaises(FrozenInstanceError, setattr, resolved, "model", "changed")

    def test_secret_is_hidden_from_config_repr(self):
        settings = replace(self.settings, qq_app_secret="private-secret")
        self.assertNotIn("private-secret", repr(settings))
