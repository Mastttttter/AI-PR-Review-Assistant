from __future__ import annotations

import logging
import re

import pytest

from apr_backend.core.logging_config import SensitiveDataFilter, configure_app_logging
from apr_backend.services.llm_adapter import REVIEW_PROMPT_PREVIEW_LENGTH, _redact_for_log


class TestRedactForLog:
    def test_short_text_returns_unchanged(self) -> None:
        text = "hello world"
        assert _redact_for_log(text) == text

    def test_long_text_is_truncated_with_suffix(self) -> None:
        text = "x" * 500
        result = _redact_for_log(text)
        assert len(result) <= REVIEW_PROMPT_PREVIEW_LENGTH + 50  # approx suffix length
        assert "[truncated, total length=500]" in result

    def test_exact_boundary_text(self) -> None:
        text = "x" * REVIEW_PROMPT_PREVIEW_LENGTH
        result = _redact_for_log(text)
        assert "[truncated" not in result

    def test_boundary_plus_one_is_truncated(self) -> None:
        text = "x" * (REVIEW_PROMPT_PREVIEW_LENGTH + 1)
        result = _redact_for_log(text)
        assert "[truncated" in result
        assert len(text) > REVIEW_PROMPT_PREVIEW_LENGTH

    def test_short_text_with_custom_max_length(self) -> None:
        text = "short message"
        result = _redact_for_log(text, max_length=5)
        assert "short" in result
        assert "[truncated, total length=13]" in result

    def test_empty_text(self) -> None:
        assert _redact_for_log("") == ""

    def test_output_has_total_length(self) -> None:
        text = "abc" * 100
        result = _redact_for_log(text, max_length=10)
        assert "total length=300" in result


class TestSensitiveDataFilter:
    @pytest.fixture
    def filter(self) -> SensitiveDataFilter:
        return SensitiveDataFilter()

    def test_redact_bearer_token(self, filter) -> None:
        msg = "Authorization: Bearer sk-abc123def456ghijklmnopqrstuv"
        result = filter._redact_value(msg)
        assert "sk-abc123def456ghijklmnopqrstuv" not in result
        assert "[redacted]" in result

    def test_redact_api_key_pattern(self, filter) -> None:
        msg = "api_key=sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123456"
        result = filter._redact_value(msg)
        assert "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ123456" not in result
        assert "[redacted]" in result

    def test_redact_standalone_sk_key(self, filter) -> None:
        msg = "key is sk-this-is-a-test-key-12345"
        result = filter._redact_value(msg)
        assert "sk-this-is-a-test-key-12345" not in result
        assert "[redacted-api-key]" in result

    def test_preserves_safe_text(self, filter) -> None:
        msg = "Worker picked up review job for task abc-def-123"
        result = filter._redact_value(msg)
        assert result == msg

    def test_filter_modifies_log_record(self, filter) -> None:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Bearer sk-secret-key-minimum-20chars", args=(), exc_info=None,
        )
        filter.filter(record)
        assert "sk-secret-key-minimum-20chars" not in record.msg
        assert "Bearer [redacted]" in record.msg

    def test_filter_redacts_args(self, filter) -> None:
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="LLM call failed: %s", args=("api_key=sk-secret-api-key-above-20chars",), exc_info=None,
        )
        filter.filter(record)
        assert isinstance(record.args, tuple)
        assert "sk-secret-api-key-above-20chars" not in str(record.args[0])

    def test_filter_skips_short_string_args(self, filter) -> None:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="task id: %s", args=("abc-123",), exc_info=None,
        )
        filter.filter(record)
        assert record.args == ("abc-123",)  # unchanged

    def test_filter_handles_none_args(self, filter) -> None:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="task started", args=None, exc_info=None,
        )
        filter.filter(record)  # should not raise

    def test_filter_truncates_long_exception_message(self, filter) -> None:
        long_msg = "x" * 600
        exc = ValueError(long_msg)
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error occurred", args=(), exc_info=(ValueError, exc, None),
        )
        filter.filter(record)
        assert record.exc_info is not None
        assert len(str(record.exc_info[1])) <= 520  # 500 + "[truncated]"


class TestLoggingConfiguration:
    def test_configure_app_logging_is_idempotent_and_registers_filter(self) -> None:
        logger = logging.getLogger("apr_backend")
        before_count = len(logger.filters)
        configure_app_logging()
        after_count = len(logger.filters)
        has_filter = any(isinstance(f, SensitiveDataFilter) for f in logger.filters)
        assert has_filter
        assert after_count >= before_count
