from __future__ import annotations

from uuid import uuid4

import pytest

from apr_backend.db.enums import RuleType, Severity
from apr_backend.db.models import ReviewRule
from apr_backend.services.diff_parser import parse_diff
from apr_backend.services.rule_engine import (
    BANNED_PATTERNS,
    RULE_CHECKERS,
    SECURITY_SENSITIVE_PATTERNS,
    RuleMatch,
    _check_banned_content,
    _check_missing_tests,
    _check_security_keywords,
    _check_naming,
    _check_documentation,
    _check_module_constraint,
    run_rule_engine,
)


def _rule(**overrides) -> ReviewRule:
    defaults = dict(
        id=str(uuid4()),
        name="Test Rule",
        description="A test rule",
        rule_type=RuleType.style,
        severity=Severity.medium,
        enabled=True,
        demo_owner="test-owner",
    )
    defaults.update(overrides)
    return ReviewRule(**defaults)


DIFF_WITH_CONSOLE_LOG = """\
diff --git a/src/app.ts b/src/app.ts
--- a/src/app.ts
+++ b/src/app.ts
@@ -5,3 +5,4 @@
 function init() {
+  console.log("ready");
 }
"""

DIFF_WITHOUT_TESTS = """\
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,4 @@
 def login(user):
+    token = generate_token(user)
     return token
"""

DIFF_WITH_TESTS = """\
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,4 @@
 def login(user):
+    token = generate_token(user)
     return token
diff --git a/tests/test_auth.py b/tests/test_auth.py
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,2 @@
+def test_login():
+    pass
"""

DIFF_WITH_EMPTY_FILE = """\
diff --git a/empty.txt b/empty.txt
deleted file mode 100644
--- a/empty.txt
+++ /dev/null
@@ -1 +0,0 @@
-
"""

DIFF_WITH_HARDCODED_SECRET = """\
diff --git a/src/config.py b/src/config.py
--- a/src/config.py
+++ b/src/config.py
@@ -1,2 +1,3 @@
+API_KEY = "sk-1234567890abcdef"
 DEBUG = True
"""

DIFF_WITH_GENERIC_NAMES = """\
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,2 +1,3 @@
+data = fetch_items()
+tmp = data[0]
"""

DIFF_WITH_NEW_FUNCTION_NO_DOCSTRING = """\
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,1 +1,4 @@
+def process_items(items):
+    result = []
+    for item in items:
+        result.append(item.upper())
"""

DIFF_CONTROLLER_DB_DIRECT = """\
diff --git a/src/controllers/user_controller.py b/src/controllers/user_controller.py
--- a/src/controllers/user_controller.py
+++ b/src/controllers/user_controller.py
@@ -5,3 +5,4 @@
 def get_user(id):
+    result = db.execute("SELECT * FROM users WHERE id = ?", id)
     return format_user(result)
"""


class TestBannedContent:
    def test_detects_console_log(self) -> None:
        rule = _rule(rule_type=RuleType.style, severity=Severity.low)
        matches = _check_banned_content(rule, DIFF_WITH_CONSOLE_LOG)
        assert len(matches) == 1
        assert matches[0].rule_id == rule.id
        assert "console.log" in matches[0].description

    def test_no_match_on_clean_diff(self) -> None:
        rule = _rule(rule_type=RuleType.style)
        matches = _check_banned_content(rule, DIFF_WITHOUT_TESTS)
        assert len(matches) == 0


class TestMissingTests:
    def test_flags_diff_without_test_files(self) -> None:
        rule = _rule(rule_type=RuleType.test, severity=Severity.medium)
        matches = _check_missing_tests(rule, parse_diff(DIFF_WITHOUT_TESTS))
        assert len(matches) == 1
        assert matches[0].rule_type == RuleType.test

    def test_no_match_when_test_files_present(self) -> None:
        rule = _rule(rule_type=RuleType.test)
        matches = _check_missing_tests(rule, parse_diff(DIFF_WITH_TESTS))
        assert len(matches) == 0

    def test_no_match_on_empty_diff(self) -> None:
        rule = _rule(rule_type=RuleType.test)
        matches = _check_missing_tests(rule, parse_diff(""))
        assert len(matches) == 0


class TestSecurityKeywords:
    def test_detects_hardcoded_secret(self) -> None:
        rule = _rule(rule_type=RuleType.security, severity=Severity.high)
        matches = _check_security_keywords(rule, DIFF_WITH_HARDCODED_SECRET)
        assert len(matches) >= 1
        assert any("api" in m.description.lower() for m in matches)

    def test_no_match_on_clean_diff(self) -> None:
        rule = _rule(rule_type=RuleType.security)
        matches = _check_security_keywords(rule, DIFF_WITHOUT_TESTS)
        assert len(matches) == 0


class TestNaming:
    def test_detects_generic_names_in_added_lines(self) -> None:
        rule = _rule(rule_type=RuleType.naming, severity=Severity.low)
        matches = _check_naming(rule, DIFF_WITH_GENERIC_NAMES)
        assert len(matches) >= 1

    def test_no_match_on_clean_diff(self) -> None:
        rule = _rule(rule_type=RuleType.naming)
        matches = _check_naming(rule, DIFF_WITHOUT_TESTS)
        assert len(matches) == 0


class TestDocumentation:
    def test_detects_new_function_without_docstring(self) -> None:
        rule = _rule(rule_type=RuleType.documentation, severity=Severity.low)
        matches = _check_documentation(rule, DIFF_WITH_NEW_FUNCTION_NO_DOCSTRING)
        assert len(matches) >= 1

    def test_no_match_on_diff_without_new_functions(self) -> None:
        rule = _rule(rule_type=RuleType.documentation)
        matches = _check_documentation(rule, DIFF_WITH_CONSOLE_LOG)
        assert len(matches) == 0


class TestModuleConstraint:
    def test_detects_db_access_in_controller(self) -> None:
        rule = _rule(rule_type=RuleType.module, severity=Severity.medium)
        matches = _check_module_constraint(rule, parse_diff(DIFF_CONTROLLER_DB_DIRECT))
        assert len(matches) == 1
        assert "controllers" in matches[0].file_path

    def test_no_match_on_non_controller_files(self) -> None:
        rule = _rule(rule_type=RuleType.module)
        matches = _check_module_constraint(rule, parse_diff(DIFF_WITHOUT_TESTS))
        assert len(matches) == 0


class TestDisabledRules:
    def test_disabled_rule_produces_no_matches(self) -> None:
        disabled = _rule(rule_type=RuleType.style, enabled=False)
        enabled = _rule(rule_type=RuleType.test, enabled=True)
        diff = parse_diff(DIFF_WITH_CONSOLE_LOG)
        matches = run_rule_engine([disabled, enabled], diff, DIFF_WITH_CONSOLE_LOG)
        rule_ids = {m.rule_id for m in matches}
        assert disabled.id not in rule_ids

    def test_all_disabled_returns_empty(self) -> None:
        rules = [
            _rule(rule_type=RuleType.style, enabled=False),
            _rule(rule_type=RuleType.security, enabled=False),
        ]
        diff = parse_diff(DIFF_WITH_HARDCODED_SECRET)
        matches = run_rule_engine(rules, diff, DIFF_WITH_HARDCODED_SECRET)
        assert len(matches) == 0


class TestRuleEngineIntegration:
    def test_multiple_enabled_rules(self) -> None:
        rules = [
            _rule(id="r1", rule_type=RuleType.style, severity=Severity.low, enabled=True),
            _rule(id="r2", rule_type=RuleType.test, severity=Severity.medium, enabled=True),
        ]
        diff = parse_diff(DIFF_WITH_CONSOLE_LOG)
        matches = run_rule_engine(rules, diff, DIFF_WITH_CONSOLE_LOG)
        rule_ids = {m.rule_id for m in matches}
        assert "r1" in rule_ids
        assert "r2" in rule_ids

    def test_unknown_rule_type_is_skipped(self) -> None:
        rule = _rule(rule_type=RuleType.style, enabled=True)
        rule.rule_type = "nonexistent"
        matches = run_rule_engine([rule], parse_diff(DIFF_WITH_CONSOLE_LOG), DIFF_WITH_CONSOLE_LOG)
        assert len(matches) == 0

    def test_rule_match_has_required_fields(self) -> None:
        rule = _rule(id="required-test", rule_type=RuleType.style, severity=Severity.low)
        matches = _check_banned_content(rule, DIFF_WITH_CONSOLE_LOG)
        assert len(matches) > 0
        m = matches[0]
        assert m.rule_id == "required-test"
        assert m.rule_type == RuleType.style
        assert m.severity == Severity.low
        assert len(m.description) > 0

    def test_deleted_only_files_no_missing_test_warning(self) -> None:
        rule = _rule(rule_type=RuleType.test)
        matches = _check_missing_tests(rule, parse_diff(DIFF_WITH_EMPTY_FILE))
        assert len(matches) == 0


class TestRuleCheckersCoverage:
    def test_all_rule_types_have_checkers(self) -> None:
        for rt in RuleType:
            assert rt in RULE_CHECKERS, f"Missing checker for {rt}"
