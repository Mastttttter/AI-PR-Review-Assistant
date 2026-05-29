from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx
from httpx import Response

from apr_backend.core.settings import get_settings
from apr_backend.services.llm_adapter import (
    LLMError,
    LLMResponseError,
    LLMTimeoutError,
    MockLLMProvider,
    OpenAICompatibleProvider,
    _redact_for_log,
    create_llm_provider,
)

SAMPLE_PROMPT = "Review this PR: adds token refresh logic."


class TestMockLLMProvider:
    def test_returns_valid_structure(self) -> None:
        provider = MockLLMProvider()
        result = provider.generate_review(SAMPLE_PROMPT)
        assert "summary" in result
        assert "risk" in result
        assert "issues" in result

    def test_summary_has_required_fields(self) -> None:
        result = MockLLMProvider().generate_review(SAMPLE_PROMPT)
        summary = result["summary"]
        assert "purpose" in summary
        assert "changed_modules" in summary
        assert "key_files" in summary

    def test_risk_has_level_and_reasons(self) -> None:
        result = MockLLMProvider().generate_review(SAMPLE_PROMPT)
        risk = result["risk"]
        assert risk["level"] in ("low", "medium", "high")
        assert isinstance(risk["reasons"], list)

    def test_issues_list_is_present(self) -> None:
        result = MockLLMProvider().generate_review(SAMPLE_PROMPT)
        assert isinstance(result["issues"], list)
        if result["issues"]:
            issue = result["issues"][0]
            assert "title" in issue
            assert "type" in issue
            assert "severity" in issue
            assert "description" in issue
            assert "suggestion" in issue

    def test_can_be_used_multiple_times(self) -> None:
        provider = MockLLMProvider()
        r1 = provider.generate_review("prompt a")
        r2 = provider.generate_review("prompt b")
        assert r1 == r2
        assert r1 is not r2


class TestOpenAICompatibleProvider:
    @pytest.fixture
    def provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
            model="test-model",
            timeout=30,
        )

    @pytest.fixture
    def mock_api(self):
        with respx.mock(base_url="https://api.example.com/v1") as mock:
            yield mock

    def test_successful_call(self, provider, mock_api) -> None:
        mock_api.post("/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({
                                    "summary": {"purpose": "test"},
                                    "risk": {"level": "low", "reasons": ["test"]},
                                    "issues": [],
                                })
                            }
                        }
                    ]
                },
            )
        )

        result = provider.generate_review(SAMPLE_PROMPT)
        assert result["summary"]["purpose"] == "test"
        assert result["risk"]["level"] == "low"

    def test_timeout_raises_llm_timeout_error(self, provider, mock_api) -> None:
        mock_api.post("/chat/completions").mock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(LLMTimeoutError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_http_error_raises_llm_response_error(self, provider, mock_api) -> None:
        mock_api.post("/chat/completions").mock(return_value=Response(500, json={"error": "server error"}))

        with pytest.raises(LLMResponseError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_invalid_json_response_raises_llm_response_error(self, provider, mock_api) -> None:
        mock_api.post("/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "not valid json!!!"}}]},
            )
        )

        with pytest.raises(LLMResponseError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_network_error_raises_llm_response_error(self, provider, mock_api) -> None:
        mock_api.post("/chat/completions").mock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(LLMResponseError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_uses_bearer_auth_header(self, provider, mock_api) -> None:
        mock_api.post("/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps({"summary": {}, "risk": {"level": "low", "reasons": []}, "issues": []})}}
                    ]
                },
            )
        )

        provider.generate_review(SAMPLE_PROMPT)
        request = mock_api.calls.last.request
        assert request.headers["Authorization"] == "Bearer sk-test-key"


class TestRedactedLogging:
    def test_short_text_is_not_redacted(self) -> None:
        assert _redact_for_log("hello", 100) == "hello"

    def test_long_text_is_redacted_with_length(self) -> None:
        result = _redact_for_log("x" * 500, 100)
        assert result.startswith("x" * 100)
        assert "truncated" in result
        assert "total length=500" in result

    def test_long_prompt_in_llm_call_is_not_fully_logged(self, caplog) -> None:
        caplog.set_level(logging.INFO)
        big_prompt = "Review: " + "A" * 2000
        MockLLMProvider().generate_review(big_prompt)
        log_text = caplog.text
        assert big_prompt not in log_text


class TestFactory:
    def test_mock_enabled_returns_mock_provider(self, monkeypatch) -> None:
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "true")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, MockLLMProvider)

    def test_no_api_key_returns_mock_provider(self, monkeypatch) -> None:
        monkeypatch.delenv("APR_LLM_API_KEY", raising=False)
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, MockLLMProvider)

    def test_api_key_without_mock_returns_openai_provider(self, monkeypatch) -> None:
        monkeypatch.setenv("APR_LLM_API_KEY", "sk-real-key")
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, OpenAICompatibleProvider)


class TestLLMErrorHierarchy:
    def test_llm_error_is_exception(self) -> None:
        with pytest.raises(LLMError):
            raise LLMError("base")

    def test_timeout_error_is_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise LLMTimeoutError("timeout")

    def test_response_error_is_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise LLMResponseError("response")
