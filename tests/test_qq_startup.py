from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from unittest.mock import patch

from ai_butler.channels import create_channel, inspect_channel
from main import main
from tests.helpers import ProjectTest


class QQStartupTests(ProjectTest):
    def test_missing_qq_credentials_are_clear(self):
        output = StringIO()
        with patch("main.config", self.settings), redirect_stdout(output):
            self.assertEqual(main(["--channel", "qq"]), 2)
        self.assertIn("QQ_APP_ID", output.getvalue())

    def test_normal_mode_requires_allowlist(self):
        settings = replace(self.settings, qq_app_id="123", qq_app_secret="secret")
        with self.assertRaisesRegex(ValueError, "QQ_ALLOWED_USERS"):
            create_channel("qq", settings=settings)

    @patch("ai_butler.channels.qq.channel._QQClient")
    def test_check_does_not_require_model_key_or_send_messages(self, client):
        settings = replace(
            self.settings, qq_app_id="123", qq_app_secret="secret", deepseek_api_key=""
        )
        with redirect_stdout(StringIO()):
            inspect_channel("qq", settings=settings)
        client.return_value.gateway_url.assert_called_once()
        client.return_value.send_text.assert_not_called()

    @patch("ai_butler.channels.qq.channel._QQGateway")
    @patch("ai_butler.channels.qq.channel._QQClient")
    def test_discovery_does_not_require_model_key(self, client, gateway):
        settings = replace(
            self.settings, qq_app_id="123", qq_app_secret="secret", deepseek_api_key=""
        )
        with redirect_stdout(StringIO()):
            inspect_channel("qq", discover=True, settings=settings)
        gateway.return_value.run.assert_called_once()
        gateway.return_value.close.assert_called_once()
        client.return_value.send_text.assert_not_called()

    def test_secret_is_hidden_from_config_repr(self):
        settings = replace(self.settings, qq_app_secret="private-secret")
        self.assertNotIn("private-secret", repr(settings))
