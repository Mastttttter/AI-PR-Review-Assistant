from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apr_backend.db.enums import Confidence, IssueType, RiskLevel, Severity

VALID_RISK_LEVELS: set[str] = {"low", "medium", "high"}
VALID_ISSUE_TYPES: set[str] = {"logic", "exception", "security", "performance", "maintainability", "test_missing", "rule_violation"}
VALID_SEVERITIES: set[str] = {"low", "medium", "high"}
VALID_CONFIDENCES: set[str] = {"low", "medium", "high"}

SEVERITY_SORT_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

REQUIRED_SUMMARY_FIELDS: set[str] = {"purpose", "changed_modules", "key_files", "business_impact", "test_or_security_notes"}
REQUIRED_RISK_FIELDS: set[str] = {"level", "reasons"}
REQUIRED_ISSUE_FIELDS: set[str] = {"title", "type", "severity", "description", "suggestion"}


@dataclass
class Location:
    file_path: str | None = None
    line_hint: str | None = None
    code_snippet: str | None = None


@dataclass
class ValidatedIssue:
    title: str
    issue_type: IssueType
    severity: Severity
    description: str
    suggestion: str
    confidence: Confidence
    file_path: str | None = None
    line_hint: str | None = None
    code_snippet: str | None = None
    matched_rule_ids: list[str] = field(default_factory=list)


@dataclass
class ValidatedSummary:
    purpose: str
    changed_modules: list[str] = field(default_factory=list)
    key_files: list[str] = field(default_factory=list)
    business_impact: str = ""
    test_or_security_notes: str = ""


@dataclass
class ValidatedRisk:
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)


@dataclass
class ValidatedReview:
    summary: ValidatedSummary
    risk: ValidatedRisk
    issues: list[ValidatedIssue]
    raw: dict[str, Any]


def _normalize_risk_level(value: str) -> RiskLevel:
    v = value.strip().lower()
    return RiskLevel(v) if v in VALID_RISK_LEVELS else RiskLevel.low


def _normalize_issue_type(value: str) -> IssueType:
    v = value.strip().lower()
    return IssueType(v) if v in VALID_ISSUE_TYPES else IssueType.maintainability


def _normalize_severity(value: str) -> Severity:
    v = value.strip().lower()
    return Severity(v) if v in VALID_SEVERITIES else Severity.low


def _normalize_confidence(value: str) -> Confidence:
    v = value.strip().lower()
    return Confidence(v) if v in VALID_CONFIDENCES else Confidence.medium


def _coerce_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


def _coerce_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is not None:
        return str(value)
    return default


def _normalize_location(raw: dict) -> Location:
    if not isinstance(raw, dict):
        return Location()
    return Location(
        file_path=_coerce_str(raw.get("file_path")) or None,
        line_hint=_coerce_str(raw.get("line_hint")) or None,
        code_snippet=_coerce_str(raw.get("code_snippet")) or None,
    )


def validate_ai_output(raw: dict[str, Any], valid_rule_ids: set[str] | None = None) -> ValidatedReview:
    if not isinstance(raw, dict):
        raw = {}

    valid_rule_ids = valid_rule_ids or set()

    summary = _validate_summary(raw.get("summary"))
    risk = _validate_risk(raw.get("risk"))
    issues = _validate_issues(raw.get("issues"), valid_rule_ids)

    return ValidatedReview(summary=summary, risk=risk, issues=issues, raw=raw)


def _validate_summary(raw: Any) -> ValidatedSummary:
    if not isinstance(raw, dict):
        return ValidatedSummary(purpose="No summary provided.")

    return ValidatedSummary(
        purpose=_coerce_str(raw.get("purpose"), "No purpose provided."),
        changed_modules=_coerce_list(raw.get("changed_modules")),
        key_files=_coerce_list(raw.get("key_files")),
        business_impact=_coerce_str(raw.get("business_impact"), ""),
        test_or_security_notes=_coerce_str(raw.get("test_or_security_notes"), ""),
    )


def _validate_risk(raw: Any) -> ValidatedRisk:
    if not isinstance(raw, dict):
        return ValidatedRisk(level=RiskLevel.low, reasons=["No risk assessment provided."])

    level_raw = raw.get("level", "low")
    reasons_raw = raw.get("reasons", [])

    return ValidatedRisk(
        level=_normalize_risk_level(_coerce_str(level_raw, "low")),
        reasons=_coerce_list(reasons_raw) if _coerce_list(reasons_raw) else ["No reasons provided."],
    )


def _validate_issues(raw: Any, valid_rule_ids: set[str]) -> list[ValidatedIssue]:
    if not isinstance(raw, list):
        return []

    valid: list[ValidatedIssue] = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        description = _coerce_str(item.get("description"), "")
        suggestion = _coerce_str(item.get("suggestion"), "")

        if not description.strip():
            continue

        if not suggestion.strip():
            suggestion = "Review and consider improvements."

        title = _coerce_str(item.get("title"), "Untitled issue")
        location = _normalize_location(item.get("location"))

        matched = set()
        raw_matched = item.get("matched_rule_ids")
        if isinstance(raw_matched, list):
            matched = {r for r in raw_matched if isinstance(r, str) and r in valid_rule_ids}

        valid.append(ValidatedIssue(
            title=title,
            issue_type=_normalize_issue_type(_coerce_str(item.get("type"), "maintainability")),
            severity=_normalize_severity(_coerce_str(item.get("severity"), "low")),
            description=description,
            suggestion=suggestion,
            confidence=_normalize_confidence(_coerce_str(item.get("confidence"), "medium")),
            file_path=location.file_path,
            line_hint=location.line_hint,
            code_snippet=location.code_snippet,
            matched_rule_ids=list(matched),
        ))

    valid.sort(key=lambda i: SEVERITY_SORT_ORDER.get(i.severity.value, 99))
    return valid
