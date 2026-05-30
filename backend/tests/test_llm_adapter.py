from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx
from httpx import Response

from apr_backend.core.config_loader import load_llm_config
from apr_backend.core.settings import get_settings
from apr_backend.services.llm_adapter import (
    LLMError,
    LLMQuotaExhaustedError,
    LLMResponseError,
    LLMTimeoutError,
    AnthropicLLMProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
    _extract_rule_ids_from_prompt,
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

    def test_no_rule_matches_returns_empty_matched_rule_ids(self) -> None:
        result = MockLLMProvider().generate_review(SAMPLE_PROMPT)
        assert result["issues"][0]["matched_rule_ids"] == []

    def test_with_rule_matches_includes_rule_ids(self) -> None:
        prompt_with_rules = """\
Some prompt content

## Pre-matched Rule Results (for context)
These rules were matched deterministically. Include their rule_id values in matched_rule_ids for any related issues.
[
  {"rule_id": "rule-uuid-1", "rule_name": "Test Rule 1", "description": "...", "file_path": "...", "line_hint": "..."},
  {"rule_id": "rule-uuid-2", "rule_name": "Test Rule 2", "description": "...", "file_path": "...", "line_hint": "..."}
]

## PR Context
PR Title: Test
"""
        result = MockLLMProvider().generate_review(prompt_with_rules)
        assert result["issues"][0]["matched_rule_ids"] == ["rule-uuid-1", "rule-uuid-2"]

    def test_empty_rule_array_returns_empty_matched_rule_ids(self) -> None:
        prompt_with_empty_rules = """\
Some prompt content

## Pre-matched Rule Results (for context)
These rules were matched deterministically. Include their rule_id values in matched_rule_ids for any related issues.
[]

## PR Context
PR Title: Test
"""
        result = MockLLMProvider().generate_review(prompt_with_empty_rules)
        assert result["issues"][0]["matched_rule_ids"] == []


class TestExtractRuleIdsFromPrompt:
    def test_extracts_single_rule_id(self) -> None:
        prompt = """\
## Pre-matched Rule Results (for context)
[
  {"rule_id": "abc-123", "rule_name": "Test"}
]

## PR Context
"""
        assert _extract_rule_ids_from_prompt(prompt) == ["abc-123"]

    def test_extracts_multiple_rule_ids(self) -> None:
        prompt = """\
## Pre-matched Rule Results (for context)
[
  {"rule_id": "id-1", "rule_name": "Rule 1"},
  {"rule_id": "id-2", "rule_name": "Rule 2"},
  {"rule_id": "id-3", "rule_name": "Rule 3"}
]
"""
        assert _extract_rule_ids_from_prompt(prompt) == ["id-1", "id-2", "id-3"]

    def test_returns_empty_for_no_pre_matched_section(self) -> None:
        prompt = "Just a simple prompt without rule results."
        assert _extract_rule_ids_from_prompt(prompt) == []

    def test_returns_empty_for_empty_array(self) -> None:
        prompt = """\
## Pre-matched Rule Results (for context)
[]
"""
        assert _extract_rule_ids_from_prompt(prompt) == []

    def test_handles_malformed_json_gracefully(self) -> None:
        prompt = """\
## Pre-matched Rule Results (for context)
[not valid json
"""
        assert _extract_rule_ids_from_prompt(prompt) == []

    def test_skips_entries_without_rule_id(self) -> None:
        prompt = """\
## Pre-matched Rule Results (for context)
[
  {"rule_id": "valid-id", "rule_name": "Has ID"},
  {"rule_name": "Missing ID"}
]
"""
        assert _extract_rule_ids_from_prompt(prompt) == ["valid-id"]


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


class TestAnthropicLLMProvider:
    @pytest.fixture
    def provider(self) -> AnthropicLLMProvider:
        return AnthropicLLMProvider(
            api_key="sk-ant-test-key",
            base_url="https://api.anthropic.example.com",
            model="claude-test",
            timeout=30,
        )

    @pytest.fixture
    def mock_api(self):
        with respx.mock(base_url="https://api.anthropic.example.com") as mock:
            yield mock

    def test_successful_call(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "summary": {"purpose": "anthropic test"},
                                "risk": {"level": "medium", "reasons": ["moderate change"]},
                                "issues": [],
                            }),
                        }
                    ]
                },
            )
        )

        result = provider.generate_review(SAMPLE_PROMPT)
        assert result["summary"]["purpose"] == "anthropic test"
        assert result["risk"]["level"] == "medium"

    def test_uses_x_api_key_header(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": json.dumps({"summary": {}, "risk": {"level": "low", "reasons": []}, "issues": []})}
                    ]
                },
            )
        )

        provider.generate_review(SAMPLE_PROMPT)
        request = mock_api.calls.last.request
        assert request.headers["x-api-key"] == "sk-ant-test-key"

    def test_uses_anthropic_version_header(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": json.dumps({"summary": {}, "risk": {"level": "low", "reasons": []}, "issues": []})}
                    ]
                },
            )
        )

        provider.generate_review(SAMPLE_PROMPT)
        request = mock_api.calls.last.request
        assert request.headers["anthropic-version"] == "2023-06-01"

    def test_request_body_has_messages_array(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": json.dumps({"summary": {}, "risk": {"level": "low", "reasons": []}, "issues": []})}
                    ]
                },
            )
        )

        provider.generate_review(SAMPLE_PROMPT)
        request = mock_api.calls.last.request
        body = json.loads(request.content)
        assert "messages" in body
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == SAMPLE_PROMPT

    def test_request_body_has_system(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": json.dumps({"summary": {}, "risk": {"level": "low", "reasons": []}, "issues": []})}
                    ]
                },
            )
        )

        provider.generate_review(SAMPLE_PROMPT)
        request = mock_api.calls.last.request
        body = json.loads(request.content)
        assert "system" in body

    def test_request_body_has_max_tokens(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": json.dumps({"summary": {}, "risk": {"level": "low", "reasons": []}, "issues": []})}
                    ]
                },
            )
        )

        provider.generate_review(SAMPLE_PROMPT)
        request = mock_api.calls.last.request
        body = json.loads(request.content)
        assert body["max_tokens"] == 4096

    def test_timeout_raises_llm_timeout_error(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(side_effect=httpx.TimeoutException("timed out"))

        with pytest.raises(LLMTimeoutError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_http_error_raises_llm_response_error(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(return_value=Response(500, json={"error": "server error"}))

        with pytest.raises(LLMResponseError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_quota_exhausted_raises_llm_quota_exhausted_error(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(return_value=Response(429, json={"error": "rate limited"}))

        with pytest.raises(LLMQuotaExhaustedError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_invalid_json_response_raises_llm_response_error(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={"content": [{"type": "text", "text": "not valid json!!!"}]},
            )
        )

        with pytest.raises(LLMResponseError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_network_error_raises_llm_response_error(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(side_effect=httpx.ConnectError("connection refused"))

        with pytest.raises(LLMResponseError):
            provider.generate_review(SAMPLE_PROMPT)

    def test_concatenates_multiple_text_blocks(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": '{"summary": {"purpose": "block1"},'},
                        {"type": "text", "text": '"risk": {"level": "low", "reasons": []}, "issues": []}'},
                    ]
                },
            )
        )

        result = provider.generate_review(SAMPLE_PROMPT)
        assert result["summary"]["purpose"] == "block1"

    def test_skips_non_text_blocks(self, provider, mock_api) -> None:
        mock_api.post("/v1/messages").mock(
            return_value=Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": json.dumps({"summary": {"purpose": "after tool"}, "risk": {"level": "low", "reasons": []}, "issues": []})},
                    ]
                },
            )
        )

        result = provider.generate_review(SAMPLE_PROMPT)
        assert result["summary"]["purpose"] == "after tool"


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
        monkeypatch.setattr(
            "apr_backend.services.llm_adapter.load_llm_config",
            lambda: {"active_provider": "openai", "mock_enabled": True, "timeout": 60,
                     "openai": {"base_uri": "", "api_key": None, "model": ""},
                     "anthropic": {"base_uri": "", "api_key": None, "model": ""}},
        )
        provider = create_llm_provider()
        assert isinstance(provider, MockLLMProvider)

    def test_api_key_without_mock_returns_openai_provider(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.llm_adapter.load_llm_config",
            lambda: {"active_provider": "openai", "mock_enabled": False, "timeout": 60,
                     "openai": {"base_uri": "https://api.openai.com/v1", "api_key": "sk-real-key", "model": "gpt-4o-mini"},
                     "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": None, "model": "claude-sonnet-4-6"}},
        )
        provider = create_llm_provider()
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_anthropic_provider_setting_returns_anthropic_provider(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.llm_adapter.load_llm_config",
            lambda: {"active_provider": "anthropic", "mock_enabled": False, "timeout": 60,
                     "openai": {"base_uri": "https://api.openai.com/v1", "api_key": None, "model": "gpt-4o-mini"},
                     "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": "sk-ant-key", "model": "claude-sonnet-4-6"}},
        )
        provider = create_llm_provider()
        assert isinstance(provider, AnthropicLLMProvider)

    def test_openai_provider_setting_returns_openai_provider(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.llm_adapter.load_llm_config",
            lambda: {"active_provider": "openai", "mock_enabled": False, "timeout": 60,
                     "openai": {"base_uri": "https://api.openai.com/v1", "api_key": "sk-key", "model": "gpt-4o-mini"},
                     "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": None, "model": "claude-sonnet-4-6"}},
        )
        provider = create_llm_provider()
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_unknown_provider_defaults_to_openai(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.llm_adapter.load_llm_config",
            lambda: {"active_provider": "some-unknown-provider", "mock_enabled": False, "timeout": 60,
                     "openai": {"base_uri": "https://api.openai.com/v1", "api_key": "sk-key", "model": "gpt-4o-mini"},
                     "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": None, "model": "claude-sonnet-4-6"}},
        )
        provider = create_llm_provider()
        assert isinstance(provider, OpenAICompatibleProvider)


class TestFactoryConfigJson:
    def test_system_prompt_from_config_json(self, monkeypatch, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        config_path.write_text(json.dumps({
            "system_prompt": "Custom system prompt for testing.",
            "mock_enabled": True,
        }))
        get_settings.cache_clear()
        config = load_llm_config()
        get_settings.cache_clear()
        assert config["system_prompt"] == "Custom system prompt for testing."

    def test_system_prompt_from_env_var(self, monkeypatch) -> None:
        from types import SimpleNamespace
        monkeypatch.setattr(
            "apr_backend.core.settings.get_settings",
            lambda: SimpleNamespace(
                llm_provider="openai", llm_mock_enabled=True, llm_timeout=60,
                system_prompt="Env system prompt.",
                openai_base_uri="", openai_api_key=None, openai_model="",
                anthropic_base_uri="", anthropic_api_key=None, anthropic_model="",
                llm_api_key=None,
            ),
        )
        get_settings.cache_clear()
        config = load_llm_config()
        get_settings.cache_clear()
        assert config["system_prompt"] == "Env system prompt."

    def test_system_prompt_default_empty(self, monkeypatch) -> None:
        from types import SimpleNamespace
        monkeypatch.setattr(
            "apr_backend.core.settings.get_settings",
            lambda: SimpleNamespace(
                llm_provider="openai", llm_mock_enabled=True, llm_timeout=60,
                system_prompt="",
                openai_base_uri="", openai_api_key=None, openai_model="",
                anthropic_base_uri="", anthropic_api_key=None, anthropic_model="",
                llm_api_key=None,
            ),
        )
        get_settings.cache_clear()
        config = load_llm_config()
        get_settings.cache_clear()
        assert config["system_prompt"] == ""

    def test_uses_config_json_values_when_present(self, monkeypatch, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        config_path.write_text(json.dumps({
            "active_provider": "anthropic",
            "openai": {"base_uri": "https://openai.example.com", "api_key": "sk-openai-cfg", "model": "gpt-5"},
            "anthropic": {"base_uri": "https://anthropic.example.com", "api_key": "sk-ant-cfg", "model": "claude-opus"},
        }))
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, AnthropicLLMProvider)
        assert provider._base_url == "https://anthropic.example.com"
        assert provider._model == "claude-opus"

    def test_falls_back_to_env_vars_when_no_config_file(self, monkeypatch) -> None:
        monkeypatch.setenv("APR_LLM_API_KEY", "sk-legacy")
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        monkeypatch.setenv("APR_LLM_PROVIDER", "openai")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_mock_bypass_when_mock_enabled(self, monkeypatch, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        config_path.write_text(json.dumps({
            "openai": {"base_uri": "https://openai.example.com", "api_key": "sk-openai", "model": "gpt-4"},
        }))
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "true")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, MockLLMProvider)

    def test_missing_config_json_does_not_crash(self, monkeypatch, tmp_path) -> None:
        config_path = tmp_path / "nonexistent" / "config.json"
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        monkeypatch.setenv("APR_LLM_API_KEY", "sk-legacy")
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_malformed_config_json_falls_back_gracefully(self, monkeypatch, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        config_path.write_text("{invalid json!!!")
        monkeypatch.setenv("APR_LLM_API_KEY", "sk-legacy")
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_config_json_overrides_env_vars(self, monkeypatch, tmp_path) -> None:
        config_path = tmp_path / "config.json"
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        config_path.write_text(json.dumps({
            "active_provider": "openai",
            "openai": {"base_uri": "https://cfg.openai.com", "api_key": "sk-cfg", "model": "cfg-model"},
        }))
        monkeypatch.setenv("APR_OPENAI_BASE_URI", "https://env.openai.com")
        monkeypatch.setenv("APR_OPENAI_API_KEY", "sk-env-key")
        monkeypatch.setenv("APR_OPENAI_MODEL", "env-model")
        monkeypatch.setenv("APR_LLM_MOCK_ENABLED", "false")
        get_settings.cache_clear()
        provider = create_llm_provider()
        get_settings.cache_clear()
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._base_url == "https://cfg.openai.com"
        assert provider._model == "cfg-model"

    def test_provider_specific_env_vars_as_fallback(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.services.llm_adapter.load_llm_config",
            lambda: {"active_provider": "anthropic", "mock_enabled": False, "timeout": 60,
                     "openai": {"base_uri": "https://api.openai.com/v1", "api_key": None, "model": "gpt-4o-mini"},
                     "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": "sk-ant-env", "model": "claude-env-model"}},
        )
        provider = create_llm_provider()
        assert isinstance(provider, AnthropicLLMProvider)
        assert provider._model == "claude-env-model"


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

    def test_quota_exhausted_error_is_llm_error(self) -> None:
        with pytest.raises(LLMError):
            raise LLMQuotaExhaustedError("quota")
