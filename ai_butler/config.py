import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env", encoding="utf-8-sig")


@dataclass(frozen=True)
class Config:
    """启动时读取并冻结的环境快照；模型凭据和默认值由 Provider 初始化。"""

    provider: str = field(default_factory=lambda: os.getenv("BUTLER_PROVIDER", "deepseek"))
    config_version: str = field(default_factory=lambda: os.getenv("BUTLER_CONFIG_VERSION", "1"))
    model: str = field(default_factory=lambda: os.getenv("BUTLER_MODEL", ""))
    base_url: str = field(default_factory=lambda: os.getenv("BUTLER_BASE_URL", ""))
    options: Mapping[str, str] = field(default_factory=lambda: dict(os.environ), repr=False)
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("BUTLER_DB_PATH", "data/sessions.sqlite3"))
    )
    timeout: float = field(default_factory=lambda: float(os.getenv("BUTLER_TIMEOUT_SECONDS", "30")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("BUTLER_MAX_RETRIES", "2")))
    history_turns: int = field(default_factory=lambda: int(os.getenv("BUTLER_HISTORY_TURNS", "20")))
    max_output_tokens: int = field(
        default_factory=lambda: int(os.getenv("BUTLER_MAX_OUTPUT_TOKENS", "2048"))
    )
    max_tool_rounds: int = field(
        default_factory=lambda: int(os.getenv("BUTLER_MAX_TOOL_ROUNDS", "3"))
    )
    qq_app_id: str = field(default_factory=lambda: os.getenv("QQ_APP_ID", ""))
    qq_app_secret: str = field(default_factory=lambda: os.getenv("QQ_APP_SECRET", ""), repr=False)
    qq_api_base_url: str = field(
        default_factory=lambda: os.getenv("QQ_API_BASE_URL", "https://api.bot.qq.com")
    )
    qq_allowed_users: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            value.strip() for value in os.getenv("QQ_ALLOWED_USERS", "").split(",") if value.strip()
        )
    )
    qq_min_interval: float = field(
        default_factory=lambda: float(os.getenv("QQ_MIN_INTERVAL_SECONDS", "3"))
    )
    qq_reply_max_chars: int = field(
        default_factory=lambda: int(os.getenv("QQ_REPLY_MAX_CHARS", "1800"))
    )

    def __post_init__(self) -> None:
        """归一化路径和名称、复制只读选项并校验公共配置，不要求模型密钥。"""
        object.__setattr__(self, "provider", self.provider.strip().lower())
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "db_path", PROJECT_DIR / self.db_path.expanduser())
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))
        if not self.config_version.strip():
            raise ValueError("BUTLER_CONFIG_VERSION 不能为空。")
        if not 0 < self.timeout <= 300:
            raise ValueError("BUTLER_TIMEOUT_SECONDS 必须大于 0 且不超过 300。")
        if self.max_retries < 0:
            raise ValueError("BUTLER_MAX_RETRIES 不能为负数。")
        if min(self.history_turns, self.max_output_tokens, self.max_tool_rounds) < 1:
            raise ValueError("历史轮数、输出 tokens 和工具轮数必须大于 0。")

    def validate_qq(self, *, require_users: bool = True) -> None:
        """在 QQ 接入时校验凭据和平台限制；诊断模式可不要求白名单。"""
        if not self.qq_app_id or not self.qq_app_secret:
            raise ValueError("请先创建 QQ 官方机器人，在 .env 中填写 QQ_APP_ID 和 QQ_APP_SECRET。")
        if not self.qq_api_base_url.startswith("https://"):
            raise ValueError("QQ_API_BASE_URL 必须使用 HTTPS。")
        if require_users and not self.qq_allowed_users:
            raise ValueError("请先用 --discover 获取 OpenID，再填写 .env 中的 QQ_ALLOWED_USERS。")
        if not 0 <= self.qq_min_interval <= 300 or self.qq_reply_max_chars < 1:
            raise ValueError("QQ 消息间隔应在 0–300 秒之间，回复字符上限必须大于 0。")


config = Config()
