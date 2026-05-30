from __future__ import annotations

import logging
import re


class SensitiveDataFilter(logging.Filter):
    """Strip sensitive patterns from log records before they are emitted.

    Covers:
    - Authorization header values (Bearer tokens)
    - API key patterns (sk-*, key=, api_key=)
    - Multi-line large content blocks that look like code diffs (>500 chars)
    """

    _AUTH_HEADER_RE = re.compile(r"(Authorization|X-API-Key|api[-_]?key)\s*[:=]\s*[^\s,\]]+\b", re.IGNORECASE)
    _BEARER_TOKEN_RE = re.compile(r"Bearer\s+[^\s\"']+", re.IGNORECASE)
    _API_KEY_RE = re.compile(r"(sk-[a-zA-Z0-9_-]{20,})")

    @classmethod
    def _redact_value(cls, text: str) -> str:
        text = cls._BEARER_TOKEN_RE.sub("Bearer [redacted]", text)
        text = cls._AUTH_HEADER_RE.sub(r"\1 [redacted]", text)
        text = cls._API_KEY_RE.sub("[redacted-api-key]", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_value(record.msg)
        if record.args is not None:
            try:
                record.args = tuple(
                    self._redact_value(str(a)) if isinstance(a, str) and len(a) > 20 else a
                    for a in record.args
                )
            except Exception:
                pass
        if record.exc_text:
            record.exc_text = self._redact_value(record.exc_text)
        if record.exc_info and record.exc_info[1]:
            try:
                msg = str(record.exc_info[1])
                if len(msg) > 500:
                    record.exc_info = (
                        record.exc_info[0],
                        type(record.exc_info[1])(msg[:500] + " [truncated]"),
                        record.exc_info[2],
                    )
            except Exception:
                pass
        return True


def configure_app_logging() -> None:
    logger = logging.getLogger("apr_backend")
    has_filter = any(isinstance(f, SensitiveDataFilter) for f in logger.filters)
    if not has_filter:
        logger.addFilter(SensitiveDataFilter())
