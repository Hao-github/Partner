import platform
from importlib.metadata import version
from typing import Any

from ..config import Config, config


def get_version(settings: Config = config) -> dict[str, Any]:
    """只返回版本和模型标识，不导出配置快照、路径或凭据。"""
    return {
        "application_version": version("gptpartner-ai-butler"),
        "config_version": settings.config_version,
        "model": {
            "provider": settings.provider,
            "version": settings.model,
            "version_source": "configured_model_id",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "conda": settings.options.get("CONDA_DEFAULT_ENV", ""),
            "mcp": version("mcp"),
        },
    }
