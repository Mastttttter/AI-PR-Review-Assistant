from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from apr_backend.core.settings import get_settings

logger = logging.getLogger(__name__)

REVIEW_PROMPT_PREVIEW_LENGTH = 200
REVIEW_RESULT_PREVIEW_LENGTH = 200


class LLMError(Exception):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


def _redact_for_log(text: str, max_length: int = REVIEW_PROMPT_PREVIEW_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}... [truncated, total length={len(text)}]"


class LLMProvider(ABC):
    @abstractmethod
    def generate_review(self, prompt: str) -> dict[str, Any]:
        ...


def _extract_rule_ids_from_prompt(prompt: str) -> list[str]:
    """Extract rule_id values from the Pre-matched Rule Results section of the prompt."""
    match = re.search(r"## Pre-matched Rule Results.*?\n(\[.*?\])\s*\n", prompt, re.DOTALL)
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
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate_review(self, prompt: str) -> dict[str, Any]:
        logger.info("LLM call: model=%s prompt_length=%d preview=%s", self._model, len(prompt), _redact_for_log(prompt))
        url = f"{self._base_url}/chat/completions"

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
            logger.error("LLM API returned error status %d", exc.response.status_code)
            raise LLMResponseError(f"LLM API error: {exc.response.status_code}")
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


def create_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_mock_enabled or settings.llm_api_key is None:
        logger.info("Using MockLLMProvider (mock_enabled=%s, api_key_set=%s)", settings.llm_mock_enabled, settings.llm_api_key is not None)
        return MockLLMProvider()

    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout=settings.llm_timeout,
    )
