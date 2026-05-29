from __future__ import annotations

import pytest

from apr_backend.db.enums import Confidence, IssueType, RiskLevel, Severity
from apr_backend.services.ai_validator import (
    VALID_CONFIDENCES,
    VALID_ISSUE_TYPES,
    VALID_RISK_LEVELS,
    VALID_SEVERITIES,
    ValidatedIssue,
    ValidatedReview,
    validate_ai_output,
)

VALID_OUTPUT = {
    "summary": {
        "purpose": "Add token refresh logic.",
        "changed_modules": ["auth", "api"],
        "key_files": ["src/auth.py", "src/token.py"],
        "business_impact": "Users stay logged in longer.",
        "test_or_security_notes": "Tests are included; auth logic changed.",
    },
    "risk": {
        "level": "medium",
        "reasons": [
            "Modifies authentication logic.",
            "New token flow without full test coverage.",
        ],
    },
    "issues": [
        {
            "title": "Missing input validation",
            "type": "logic",
            "severity": "high",
            "description": "The login function does not validate the user parameter before use.",
            "location": {
                "file_path": "src/auth.py",
                "line_hint": "line 15",
                "code_snippet": "def login(user):",
            },
            "suggestion": "Add validation for the user parameter.",
            "confidence": "high",
            "matched_rule_ids": [],
        },
        {
            "title": "Unused import",
            "type": "maintainability",
            "severity": "low",
            "description": "The import `os` is unused.",
            "suggestion": "Remove the unused import.",
            "confidence": "high",
            "matched_rule_ids": [],
        },
    ],
}


class TestValidOutput:
    def test_valid_output_is_accepted_unchanged(self) -> None:
        result = validate_ai_output(VALID_OUTPUT)
        assert result.risk.level == RiskLevel.medium
        assert len(result.risk.reasons) == 2
        assert result.summary.purpose == "Add token refresh logic."
        assert len(result.issues) == 2
        assert result.issues[0].severity == Severity.high

    def test_issues_sorted_by_severity_high_first(self) -> None:
        result = validate_ai_output(VALID_OUTPUT)
        order = [i.severity for i in result.issues]
        assert order == [Severity.high, Severity.low]

    def test_location_fields_preserved(self) -> None:
        result = validate_ai_output(VALID_OUTPUT)
        issue = result.issues[0]
        assert issue.file_path == "src/auth.py"
        assert issue.line_hint == "line 15"
        assert issue.code_snippet == "def login(user):"


class TestInvalidEnums:
    def test_invalid_risk_level_normalized_to_low(self) -> None:
        raw = dict(VALID_OUTPUT, risk={"level": "critical", "reasons": ["test"]})
        result = validate_ai_output(raw)
        assert result.risk.level == RiskLevel.low

    def test_invalid_severity_normalized_to_low(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{"title": "x", "type": "logic", "severity": "fatal", "description": "d", "suggestion": "s"}]}
        result = validate_ai_output(raw)
        assert result.issues[0].severity == Severity.low

    def test_invalid_issue_type_normalized_to_maintainability(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{"title": "x", "type": "imaginary", "severity": "medium", "description": "d", "suggestion": "s"}]}
        result = validate_ai_output(raw)
        assert result.issues[0].issue_type == IssueType.maintainability

    def test_invalid_confidence_normalized_to_medium(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{"title": "x", "type": "logic", "severity": "low", "description": "d", "suggestion": "s", "confidence": "definitely"}]}
        result = validate_ai_output(raw)
        assert result.issues[0].confidence == Confidence.medium


class TestMissingFields:
    def test_empty_dict_produces_safe_defaults(self) -> None:
        result = validate_ai_output({})
        assert result.summary.purpose != ""
        assert result.risk.level == RiskLevel.low
        assert result.issues == []

    def test_missing_risk_defaults_to_low(self) -> None:
        raw: dict = {"summary": {"purpose": "test"}, "issues": []}
        result = validate_ai_output(raw)
        assert result.risk.level == RiskLevel.low
        assert len(result.risk.reasons) > 0

    def test_missing_issue_description_skipped(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [
                   {"title": "Good", "type": "logic", "severity": "low", "description": "desc", "suggestion": "fix"},
                   {"title": "Bad", "type": "logic", "severity": "high", "description": "", "suggestion": "fix"},
               ]}
        result = validate_ai_output(raw)
        assert len(result.issues) == 1
        assert result.issues[0].title == "Good"

    def test_missing_suggestion_gets_default(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{"title": "x", "type": "logic", "severity": "low", "description": "desc"}]}
        result = validate_ai_output(raw)
        assert len(result.issues[0].suggestion) > 0


class TestUnsortedIssues:
    def test_issues_resorted_severity_high_first(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [
                   {"title": "Low", "type": "logic", "severity": "low", "description": "d", "suggestion": "s"},
                   {"title": "High", "type": "logic", "severity": "high", "description": "d", "suggestion": "s"},
                   {"title": "Medium", "type": "logic", "severity": "medium", "description": "d", "suggestion": "s"},
               ]}
        result = validate_ai_output(raw)
        order = [i.severity.value for i in result.issues]
        assert order == ["high", "medium", "low"]

    def test_unsorted_issues_are_reordered(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [
                   {"title": "L", "type": "logic", "severity": "low", "description": "d", "suggestion": "s"},
                   {"title": "H", "type": "logic", "severity": "high", "description": "d", "suggestion": "s"},
               ]}
        result = validate_ai_output(raw)
        assert result.issues[0].title == "H"
        assert result.issues[1].title == "L"


class TestStaleRuleIDs:
    def test_unknown_rule_ids_are_stripped(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{
                   "title": "x", "type": "logic", "severity": "low", "description": "d", "suggestion": "s",
                   "matched_rule_ids": ["valid-1", "stale-1", "stale-2"],
               }]}
        result = validate_ai_output(raw, valid_rule_ids={"valid-1"})
        assert result.issues[0].matched_rule_ids == ["valid-1"]

    def test_all_unknown_rule_ids_produces_empty_list(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{
                   "title": "x", "type": "logic", "severity": "low", "description": "d", "suggestion": "s",
                   "matched_rule_ids": ["stale"],
               }]}
        result = validate_ai_output(raw, valid_rule_ids=set())
        assert result.issues[0].matched_rule_ids == []

    def test_non_list_matched_rules_handled(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{
                   "title": "x", "type": "logic", "severity": "low", "description": "d", "suggestion": "s",
                   "matched_rule_ids": "not-a-list",
               }]}
        result = validate_ai_output(raw)
        assert result.issues[0].matched_rule_ids == []


class TestNonDictInput:
    def test_none_input_produces_safe_defaults(self) -> None:
        result = validate_ai_output(None)
        assert result.summary.purpose != ""
        assert result.risk.level == RiskLevel.low

    def test_list_input_produces_safe_defaults(self) -> None:
        result = validate_ai_output([])
        assert result.summary.purpose != ""

    def test_string_input_produces_safe_defaults(self) -> None:
        result = validate_ai_output("not json")
        assert result.summary.purpose != ""


class TestCoercion:
    def test_reasons_string_is_wrapped_in_list(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": {"level": "low", "reasons": "single reason"}, "issues": []}
        result = validate_ai_output(raw)
        assert result.risk.reasons == ["single reason"]

    def test_non_string_title_is_converted(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{"title": 123, "type": "logic", "severity": "low", "description": "d", "suggestion": "s"}]}
        result = validate_ai_output(raw)
        assert "123" in result.issues[0].title

    def test_location_non_dict_produces_empties(self) -> None:
        raw = {"summary": {"purpose": "t"}, "risk": VALID_OUTPUT["risk"],
               "issues": [{"title": "x", "type": "logic", "severity": "low", "description": "d", "suggestion": "s", "location": "bad"}]}
        result = validate_ai_output(raw)
        assert result.issues[0].file_path is None


class TestRawPreserved:
    def test_raw_input_is_preserved(self) -> None:
        result = validate_ai_output(VALID_OUTPUT)
        assert result.raw is VALID_OUTPUT
