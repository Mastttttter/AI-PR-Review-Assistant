from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Header, status
from pydantic import BaseModel, Field

from apr_backend.core.config_loader import _CONFIG_PATH as CONFIG_PATH
from apr_backend.core.config_loader import _mask_key, load_llm_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]

_CONFIG_DIR = CONFIG_PATH.parent


def _masked_config(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for provider in ("openai", "anthropic"):
        if provider in config and isinstance(config[provider], dict):
            masked = dict(config[provider])
            masked["api_key"] = _mask_key(config[provider].get("api_key"))
            result[provider] = masked
    for key in ("active_provider", "mock_enabled"):
        if key in config:
            result[key] = config[key]
    return result


def _is_masked_key(key: str | None) -> bool:
    if not key:
        return True
    return key.startswith("***-")


def _resolve_api_key(incoming_key: str | None, provider: str) -> str | None:
    if not incoming_key or _is_masked_key(incoming_key):
        config = load_llm_config()
        provider_cfg = config.get(provider, {})
        return provider_cfg.get("api_key") if isinstance(provider_cfg, dict) else None
    return incoming_key


class TestRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    base_uri: str = Field(min_length=1)
    api_key: str | None = None
    model: str = Field(min_length=1)


@router.get("")
def get_settings_config(demo_owner: DemoOwnerHeader) -> dict[str, Any]:
    config = load_llm_config()
    return _masked_config(config)


@router.put("")
def put_settings_config(payload: dict[str, Any], demo_owner: DemoOwnerHeader) -> dict[str, Any]:
    current = load_llm_config()
    for provider in ("openai", "anthropic"):
        if provider in payload and isinstance(payload[provider], dict):
            incoming_key = payload[provider].get("api_key")
            if _is_masked_key(incoming_key):
                existing_key = current.get(provider, {}).get("api_key")
                payload[provider]["api_key"] = existing_key

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(payload, indent=2))
    return payload


@router.post("/test")
def test_settings_connection(payload: TestRequest, demo_owner: DemoOwnerHeader) -> dict[str, Any]:
    base_uri = payload.base_uri.rstrip("/")
    provider = payload.provider.lower()
    api_key = _resolve_api_key(payload.api_key, provider)
    if not api_key:
        return {"success": False, "message": "No API key configured for this provider"}

    if provider == "anthropic":
        url = f"{base_uri}/v1/messages"
        req_body = {
            "model": payload.model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hi"}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    else:
        url = f"{base_uri}/chat/completions"
        req_body = {
            "model": payload.model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    try:
        response = httpx.post(url, json=req_body, headers=headers, timeout=httpx.Timeout(15))
        if 200 <= response.status_code < 300:
            return {"success": True, "message": f"Connected successfully to {provider} (status {response.status_code})"}
        if response.status_code in (401, 403):
            return {"success": False, "message": f"Invalid API key (status {response.status_code})"}
        return {"success": False, "message": f"Connection failed (status {response.status_code}): {response.text[:200]}"}
    except httpx.TimeoutException:
        return {"success": False, "message": "Connection timed out"}
    except httpx.RequestError as exc:
        return {"success": False, "message": f"Connection failed: {exc}"}
