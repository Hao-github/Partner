import platform
from importlib.metadata import version
from typing import Any

from ..config import config


def get_version(
    *,
    provider: str = config.provider,
    model: str = config.model,
    config_version: str = config.config_version,
    environment: str = config.options.get("CONDA_DEFAULT_ENV", ""),
) -> dict[str, Any]:
    """只返回版本和模型标识，不导出配置快照、路径或凭据。"""
    return {
        "application_version": version("gptpartner-ai-butler"),
        "config_version": config_version,
        "model": {
            "provider": provider,
            "version": model,
            "version_source": "configured_model_id",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "conda": environment,
            "mcp": version("mcp"),
        },
    }
