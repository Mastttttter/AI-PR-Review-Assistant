from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _BACKEND_DIR / "config" / "config.json"


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 4:
        return "***-****"
    return f"***-{key[-4:]}"


def load_llm_config() -> dict[str, Any]:
    """Return merged LLM config: config.json > provider env vars > legacy env vars."""
    from apr_backend.core.settings import get_settings

    settings = get_settings()

    legacy_api_key: str | None = None
    if settings.llm_api_key is not None:
        legacy_api_key = settings.llm_api_key.get_secret_value()

    config: dict[str, Any] = {
        "active_provider": settings.llm_provider,
        "mock_enabled": settings.llm_mock_enabled,
        "timeout": settings.llm_timeout,
        "system_prompt": settings.system_prompt,
        "openai": {
            "base_uri": settings.openai_base_uri,
            "api_key": settings.openai_api_key or legacy_api_key,
            "model": settings.openai_model,
        },
        "anthropic": {
            "base_uri": settings.anthropic_base_uri,
            "api_key": settings.anthropic_api_key or legacy_api_key,
            "model": settings.anthropic_model,
        },
    }

    if _CONFIG_PATH.exists():
        try:
            file_config = json.loads(_CONFIG_PATH.read_text())
            if isinstance(file_config, dict):
                if "active_provider" in file_config:
                    config["active_provider"] = file_config["active_provider"]
                if "mock_enabled" in file_config:
                    config["mock_enabled"] = file_config["mock_enabled"]
                if "system_prompt" in file_config:
                    config["system_prompt"] = file_config["system_prompt"]
                for provider in ("openai", "anthropic"):
                    if provider in file_config and isinstance(file_config[provider], dict):
                        for key in ("base_uri", "api_key", "model"):
                            val = file_config[provider].get(key)
                            if val is not None:
                                config[provider][key] = val
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read config.json, falling back to env vars")

    return config
