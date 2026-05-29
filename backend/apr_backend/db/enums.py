from enum import StrEnum


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    deleted = "deleted"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class IssueType(StrEnum):
    logic = "logic"
    exception = "exception"
    security = "security"
    performance = "performance"
    maintainability = "maintainability"
    test_missing = "test_missing"
    rule_violation = "rule_violation"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class Confidence(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class RuleType(StrEnum):
    test = "test"
    style = "style"
    security = "security"
    documentation = "documentation"
    naming = "naming"
    module = "module"


class FeedbackStatus(StrEnum):
    none = "none"
    useful = "useful"
    useless = "useless"
    false_positive = "false_positive"
    adopted = "adopted"
    ignored = "ignored"
