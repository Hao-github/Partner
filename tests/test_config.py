import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ai_butler.config import Config, config
from ai_butler.core import agent as agent_module
from ai_butler.providers._deepseek import DeepSeekProvider
from tests.helpers import ProjectTest


class ConfigTests(ProjectTest):
    def test_fields_read_environment_with_correct_types(self):
        with patch.dict(
            os.environ,
            {
                "BUTLER_PROVIDER": "openai",
                "BUTLER_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
                "BUTLER_TIMEOUT_SECONDS": "12.5",
                "BUTLER_MAX_RETRIES": "1",
                "BUTLER_HISTORY_TURNS": "8",
            },
            clear=True,
        ):
            settings = Config()
        settings.validate()
        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.timeout, 12.5)
        self.assertEqual(settings.max_retries, 1)
        self.assertEqual(settings.history_turns, 8)
        self.assertNotIn("test-key", repr(settings))

    def test_modules_share_the_same_config_instance(self):
        provider = DeepSeekProvider()
        self.assertIs(provider.config, config)
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
                    "import json; from ai_butler.config import config; config.validate(); "
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
            replace(self.settings, deepseek_api_key="").validate()

    def test_select_model_resets_other_provider_defaults_and_preserves_source(self):
        selected = self.settings.select_model(provider=" OpenAI ", model="test-model")
        self.assertEqual(selected.provider, "openai")
        self.assertEqual(selected.base_url, "https://api.openai.com/v1")
        self.assertEqual(selected.model, "test-model")
        self.assertEqual(self.settings.provider, "deepseek")
        self.assertEqual(self.settings.base_url, "https://api.deepseek.com")
        deepseek = selected.select_model(provider="deepseek")
        self.assertEqual(deepseek.model, "deepseek-flash")
        self.assertEqual(deepseek.base_url, "https://api.deepseek.com")

    def test_select_model_keeps_same_provider_custom_endpoint(self):
        settings = replace(self.settings, base_url="https://test.invalid")
        selected = settings.select_model(model="custom-model")
        self.assertEqual(selected.base_url, "https://test.invalid")
        self.assertEqual(selected.model, "custom-model")

    def test_openai_model_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "BUTLER_MODEL"):
            replace(self.settings, provider="openai", model="", openai_api_key="test").validate()

    def test_invalid_provider_and_runtime_limits_are_rejected(self):
        for changes in (
            {"provider": "unknown"},
            {"timeout": float("nan")},
            {"timeout": 0},
            {"max_retries": -1},
            {"history_turns": 0},
            {"max_tool_rounds": 0},
            {"base_url": "http://example.com"},
            {"deepseek_api_key": "test\nheader"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.settings, **changes).validate()

    def test_secret_is_hidden_from_config_repr(self):
        settings = replace(self.settings, qq_app_secret="private-secret")
        self.assertNotIn("private-secret", repr(settings))
