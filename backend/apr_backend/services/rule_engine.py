from __future__ import annotations

import re
from dataclasses import dataclass

from apr_backend.db.enums import IssueType, RuleType, Severity
from apr_backend.db.models import ReviewRule
from apr_backend.services.diff_parser import ParsedDiff

BANNED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("console.log", re.compile(r"console\.log\s*\(", re.IGNORECASE)),
    ("debugger", re.compile(r"\bdebugger\b")),
    ("print(", re.compile(r"\bprint\s*\(")),
    ("TODO", re.compile(r"\bTODO\b")),
    ("FIXME", re.compile(r"\bFIXME\b")),
    ("HACK", re.compile(r"\bHACK\b")),
    ("XXX", re.compile(r"\bXXX\b")),
    ("console.error", re.compile(r"console\.error\s*\(", re.IGNORECASE)),
    ("console.warn", re.compile(r"console\.warn\s*\(", re.IGNORECASE)),
]

SECURITY_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("hardcoded password", re.compile(r"password\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)),
    ("hardcoded secret", re.compile(r"secret\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)),
    ("hardcoded api key", re.compile(r"api[_\s]?key\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)),
    ("hardcoded token", re.compile(r"token\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)),
    ("insecure eval", re.compile(r"\beval\s*\(", re.IGNORECASE)),
    ("raw sql string", re.compile(r"['\"]\s*(SELECT|INSERT|UPDATE|DELETE|DROP)\s+", re.IGNORECASE)),
    ("open redirect", re.compile(r"redirect\s*\(\s*request\.", re.IGNORECASE)),
]

SHORT_NAME_RE = re.compile(r"\b([a-z])[a-z]?\b")
GENERIC_NAMES: set[str] = {"data", "info", "tmp", "temp", "foo", "bar", "baz", "result", "item", "obj", "val", "value", "stuff", "thing"}

MODULE_DB_ACCESS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bdb\.execute\s*\(", re.IGNORECASE),
    re.compile(r"\bdatabase\.execute\s*\(", re.IGNORECASE),
    re.compile(r"\bsession\.execute\s*\(", re.IGNORECASE),
    re.compile(r"\bsession\.query\s*\(", re.IGNORECASE),
    re.compile(r"\.createQuery\s*\(", re.IGNORECASE),
    re.compile(r"\.raw_query\s*\(", re.IGNORECASE),
    re.compile(r"\.execute\s*\(\s*['\"]", re.IGNORECASE),
]

DOCSTRING_MISSING_FUNCTION_RE = re.compile(
    r"^\+?\s*(?:async\s+)?def\s+\w+\s*\([^)]*\)\s*:\s*\n\+?\s*(?!['\"]{3}|#)", re.MULTILINE
)

CONTROLLER_PATH_RE = re.compile(r"(^|/)(controller|handler|router)s?[/.]", re.IGNORECASE)


def _find_line_for_pattern(content: str, pattern: re.Pattern[str]) -> tuple[int, str] | None:
    for i, line in enumerate(content.split("\n"), start=1):
        if pattern.search(line):
            return i, line.strip()
    return None


def _check_banned_content(rule: ReviewRule, diff_content: str) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for name, pattern in BANNED_PATTERNS:
        result = _find_line_for_pattern(diff_content, pattern)
        if result is not None:
            line_no, snippet = result
            matches.append(RuleMatch(
                rule_id=rule.id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity=rule.severity,
                description=f"Found banned content '{name}': {snippet}",
                line_hint=f"line {line_no}",
                code_snippet=snippet,
            ))
    return matches


def _check_missing_tests(rule: ReviewRule, parsed: ParsedDiff) -> list[RuleMatch]:
    if parsed.metrics.contains_test_file:
        return []
    if not parsed.files or all(f.is_deleted for f in parsed.files):
        return []
    non_test_files = [f for f in parsed.files if not f.is_test and not f.is_deleted]
    if not non_test_files:
        return []
    paths = ", ".join(f.path for f in non_test_files[:3])
    more = f" and {len(non_test_files) - 3} more" if len(non_test_files) > 3 else ""
    return [RuleMatch(
        rule_id=rule.id,
        rule_name=rule.name,
        rule_type=rule.rule_type,
        severity=rule.severity,
        description=f"Modified non-test files ({paths}{more}) without corresponding test changes",
    )]


def _check_security_keywords(rule: ReviewRule, diff_content: str) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for name, pattern in SECURITY_SENSITIVE_PATTERNS:
        result = _find_line_for_pattern(diff_content, pattern)
        if result is not None:
            line_no, snippet = result
            matches.append(RuleMatch(
                rule_id=rule.id,
                rule_name=rule.name,
                rule_type=rule.rule_type,
                severity=rule.severity,
                description=f"Potential security issue ({name}): {snippet}",
                line_hint=f"line {line_no}",
                code_snippet=snippet,
            ))
    return matches


def _check_naming(rule: ReviewRule, diff_content: str) -> list[RuleMatch]:
    added_lines = [line[1:] for line in diff_content.split("\n") if line.startswith("+") and not line.startswith("+++")]
    matches: list[RuleMatch] = []
    for line in added_lines:
        stripped = line.strip()
        words = stripped.split()
        for word in words:
            clean = word.strip("=:;,.()[]{}'\"!")
            if clean.lower() in GENERIC_NAMES:
                matches.append(RuleMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                    severity=rule.severity,
                    description=f"Generic variable name '{clean}' found: {stripped}",
                    code_snippet=stripped,
                ))
    return matches


def _check_documentation(rule: ReviewRule, diff_content: str) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for match in DOCSTRING_MISSING_FUNCTION_RE.finditer(diff_content):
        snippet = match.group(0).strip()
        matches.append(RuleMatch(
            rule_id=rule.id,
            rule_name=rule.name,
            rule_type=rule.rule_type,
            severity=rule.severity,
            description=f"New function without docstring or comment: {snippet}",
            code_snippet=snippet,
        ))
    return matches


def _check_module_constraint(rule: ReviewRule, parsed: ParsedDiff) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for f in parsed.files:
        if not CONTROLLER_PATH_RE.search(f.path):
            continue
        for hunk in f.hunks:
            joined = hunk.content
            for pattern in MODULE_DB_ACCESS_PATTERNS:
                if pattern.search(joined):
                    matches.append(RuleMatch(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        rule_type=rule.rule_type,
                        severity=rule.severity,
                        description=f"Controller file '{f.path}' appears to access database directly",
                        file_path=f.path,
                    ))
                    break
    return matches


RULE_CHECKERS: dict[RuleType, object] = {
    RuleType.style: _check_banned_content,
    RuleType.test: _check_missing_tests,
    RuleType.security: _check_security_keywords,
    RuleType.naming: _check_naming,
    RuleType.documentation: _check_documentation,
    RuleType.module: _check_module_constraint,
}


@dataclass
class RuleMatch:
    rule_id: str
    rule_name: str
    rule_type: RuleType
    severity: Severity
    description: str
    file_path: str | None = None
    line_hint: str | None = None
    code_snippet: str | None = None


def run_rule_engine(rules: list[ReviewRule], parsed: ParsedDiff, diff_content: str) -> list[RuleMatch]:
    all_matches: list[RuleMatch] = []
    for rule in rules:
        if not rule.enabled:
            continue
        checker = RULE_CHECKERS.get(rule.rule_type)
        if checker is None:
            continue
        if rule.rule_type in (RuleType.test, RuleType.module):
            matches = checker(rule, parsed)
        else:
            matches = checker(rule, diff_content)
        all_matches.extend(matches)
    return all_matches
