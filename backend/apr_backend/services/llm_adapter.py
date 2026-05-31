from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from apr_backend.core.config_loader import load_llm_config

logger = logging.getLogger(__name__)

REVIEW_PROMPT_PREVIEW_LENGTH = 200
REVIEW_RESULT_PREVIEW_LENGTH = 200


class LLMError(Exception):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class LLMQuotaExhaustedError(LLMError):
    pass


class LLMAuthError(LLMError):
    pass


def _redact_for_log(text: str, max_length: int = REVIEW_PROMPT_PREVIEW_LENGTH) -> str:
    result = text[:max_length] if len(text) > max_length else text
    suffix = f"... [truncated, total length={len(text)}]" if len(text) > max_length else ""
    return result + suffix


class LLMProvider(ABC):
    @abstractmethod
    def generate_review(self, prompt: str) -> dict[str, Any]:
        ...


def _extract_rule_ids_from_prompt(prompt: str) -> list[str]:
    """Extract rule_id values from the Pre-matched Rule Hints or Team Rules section of the prompt."""
    match = re.search(r"## Pre-matched Rule (?:Results|Hints).*?\n(\[.*?\])\s*\n", prompt, re.DOTALL)
    if not match:
        return []
    try:
        rules = json.loads(match.group(1))
        if not isinstance(rules, list):
            return []
        return [r["rule_id"] for r in rules if isinstance(r, dict) and "rule_id" in r]
    except (json.JSONDecodeError, KeyError):
        return []


class MockLLMProvider(LLMProvider):
    def generate_review(self, prompt: str) -> dict[str, Any]:
        logger.info("MockLLM generate_review called, prompt length=%d", len(prompt))
        matched_rule_ids = _extract_rule_ids_from_prompt(prompt)
        return {
            "summary": {
                "purpose": "Mock review: this PR adds a new feature.",
                "changed_modules": ["auth", "api"],
                "key_files": ["src/auth.py"],
                "business_impact": "No breaking changes expected.",
                "test_or_security_notes": "Tests are included.",
            },
            "risk": {
                "level": "low",
                "reasons": ["Mock risk assessment: minor changes only."],
            },
            "issues": [
                {
                    "title": "Mock issue: consider adding input validation",
                    "type": "logic",
                    "severity": "low",
                    "description": "The new function accepts user input without validation.",
                    "location": {
                        "file_path": "src/auth.py",
                        "line_hint": "line 15",
                        "code_snippet": "def login(user):",
                    },
                    "suggestion": "Add validation for the user parameter before use.",
                    "confidence": "medium",
                    "matched_rule_ids": matched_rule_ids,
                }
            ],
        }


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        model: str = "gpt-4o-mini",
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate_review(self, prompt: str) -> dict[str, Any]:
        logger.info("LLM call: model=%s prompt_length=%d preview=%s", self._model, len(prompt), _redact_for_log(prompt))
        url = f"{self._base_url}/v1/chat/completions"

        try:
            response = httpx.post(
                url,
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": "You are an AI PR review assistant. Output valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self._timeout),
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.error("LLM call timed out after %ds", self._timeout)
            raise LLMTimeoutError(f"LLM request timed out after {self._timeout}s")
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error("LLM API returned error status %d", status_code)
            if status_code in (401, 403):
                raise LLMAuthError(f"LLM authentication failed: {status_code}")
            raise LLMResponseError(f"LLM API error: {status_code}")
        except httpx.RequestError as exc:
            logger.error("LLM request failed: %s", exc)
            raise LLMResponseError(f"LLM request failed: {exc}")

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("LLM returned invalid JSON. preview=%s", _redact_for_log(content, REVIEW_RESULT_PREVIEW_LENGTH))
            raise LLMResponseError(f"LLM returned invalid JSON: {exc}")

        logger.info("LLM response parsed successfully, result_preview=%s", _redact_for_log(json.dumps(result), REVIEW_RESULT_PREVIEW_LENGTH))
        return result


class AnthropicLLMProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-6",
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate_review(self, prompt: str) -> dict[str, Any]:
        logger.info("Anthropic LLM call: model=%s prompt_length=%d preview=%s", self._model, len(prompt), _redact_for_log(prompt))
        url = f"{self._base_url}/v1/messages"

        try:
            response = httpx.post(
                url,
                json={
                    "model": self._model,
                    "max_tokens": 4096,
                    "system": "You are an AI PR review assistant. Output valid JSON only.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self._timeout),
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.error("Anthropic LLM call timed out after %ds", self._timeout)
            raise LLMTimeoutError(f"LLM request timed out after {self._timeout}s")
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error("Anthropic LLM API returned error status %d", status_code)
            if status_code in (401, 403):
                raise LLMAuthError(f"LLM authentication failed: {status_code}")
            if status_code == 429:
                raise LLMQuotaExhaustedError("LLM quota exhausted: API returned 429 Too Many Requests")
            raise LLMResponseError(f"LLM API error: {status_code}")
        except httpx.RequestError as exc:
            logger.error("Anthropic LLM request failed: %s", exc)
            raise LLMResponseError(f"LLM request failed: {exc}")

        data = response.json()
        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Anthropic LLM returned invalid JSON. preview=%s", _redact_for_log(text, REVIEW_RESULT_PREVIEW_LENGTH))
            raise LLMResponseError(f"LLM returned invalid JSON: {exc}")

        logger.info("Anthropic LLM response parsed successfully, result_preview=%s", _redact_for_log(json.dumps(result), REVIEW_RESULT_PREVIEW_LENGTH))
        return result


def create_llm_provider() -> LLMProvider:
    config = load_llm_config()
    active_provider = config.get("active_provider", "openai")
    if active_provider not in ("openai", "anthropic"):
        active_provider = "openai"

    if config["mock_enabled"]:
        logger.info("Using MockLLMProvider (mock_enabled=true)")
        return MockLLMProvider()

    provider_cfg = config.get(active_provider, {})
    api_key = provider_cfg.get("api_key") if isinstance(provider_cfg, dict) else None
    if not api_key:
        logger.info("Using MockLLMProvider (no api_key for provider=%s)", active_provider)
        return MockLLMProvider()

    base_url = provider_cfg.get("base_uri", "")
    model = provider_cfg.get("model", "")
    timeout = config.get("timeout", 60)

    if active_provider == "anthropic":
        logger.info("Using AnthropicLLMProvider (model=%s, base_url=%s)", model, base_url)
        return AnthropicLLMProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    logger.info("Using OpenAICompatibleProvider (model=%s, base_url=%s)", model, base_url)
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
    )
