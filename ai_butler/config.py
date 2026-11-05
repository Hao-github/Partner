import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env", encoding="utf-8-sig")


@dataclass
class Config:
    """进程启动时从 .env / 环境变量读取；各模块共享下面的 config 实例。"""

    provider: str = field(default_factory=lambda: os.getenv("BUTLER_PROVIDER", "deepseek"))
    model: str = field(default_factory=lambda: os.getenv("BUTLER_MODEL", ""))
    base_url: str = field(default_factory=lambda: os.getenv("BUTLER_BASE_URL", ""))
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""), repr=False
    )
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)
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
        self.provider = self.provider.strip().lower()
        if not self.model and self.provider == "deepseek":
            self.model = "deepseek-flash"
        if not self.base_url:
            self.base_url = (
                "https://api.deepseek.com"
                if self.provider == "deepseek"
                else "https://api.openai.com/v1"
            )
        self.base_url = self.base_url.rstrip("/")
        self.db_path = self.db_path.expanduser()
        if not self.db_path.is_absolute():
            self.db_path = PROJECT_DIR / self.db_path

    @property
    def api_key(self) -> str:
        return self.deepseek_api_key if self.provider == "deepseek" else self.openai_api_key

    def select_model(self, *, provider: str | None = None, model: str | None = None) -> "Config":
        """按次选择模型，不修改共享配置；换供应商时重置旧模型和服务地址。"""
        name = self.provider if provider is None else provider.strip().lower()
        changed = name != self.provider
        return replace(
            self,
            provider=name,
            model=model if model is not None else ("" if changed else self.model),
            base_url="" if changed else self.base_url,
        )

    def validate(self) -> None:
        """启动服务前检查必要配置，导入模块本身不要求已填写密钥。"""
        if self.provider not in {"deepseek", "openai"}:
            raise ValueError("BUTLER_PROVIDER 只能是 deepseek 或 openai。")
        if not self.api_key.strip():
            name = "DEEPSEEK_API_KEY" if self.provider == "deepseek" else "OPENAI_API_KEY"
            raise ValueError(f"请在项目 .env 中填写 {name}。")
        if not self.api_key.isascii() or any(char.isspace() for char in self.api_key):
            raise ValueError("API Key 不能包含非 ASCII 字符或空白。")
        if not self.model.strip():
            raise ValueError("请在 .env 中设置 BUTLER_MODEL。")
        if not self.base_url.startswith("https://"):
            raise ValueError("BUTLER_BASE_URL 必须使用 HTTPS。")
        if not 0 < self.timeout <= 300:
            raise ValueError("BUTLER_TIMEOUT_SECONDS 必须大于 0 且不超过 300。")
        if self.max_retries < 0:
            raise ValueError("BUTLER_MAX_RETRIES 不能为负数。")
        if min(self.history_turns, self.max_output_tokens, self.max_tool_rounds) < 1:
            raise ValueError("历史轮数、输出 tokens 和工具轮数必须大于 0。")

    def validate_qq(self, *, require_users: bool = True) -> None:
        if not self.qq_app_id or not self.qq_app_secret:
            raise ValueError("请先创建 QQ 官方机器人，在 .env 中填写 QQ_APP_ID 和 QQ_APP_SECRET。")
        if not self.qq_api_base_url.startswith("https://"):
            raise ValueError("QQ_API_BASE_URL 必须使用 HTTPS。")
        if require_users and not self.qq_allowed_users:
            raise ValueError(
                "请先用 --qq-discover 获取 OpenID，再填写 .env 中的 QQ_ALLOWED_USERS。"
            )
        if not 0 < self.timeout <= 300 or self.max_retries < 0:
            raise ValueError("请求超时应大于 0 且不超过 300，重试次数不能为负数。")
        if not 0 <= self.qq_min_interval <= 300 or self.qq_reply_max_chars < 1:
            raise ValueError("QQ 消息间隔应在 0–300 秒之间，回复字符上限必须大于 0。")


config = Config()
