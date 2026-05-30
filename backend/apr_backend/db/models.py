from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apr_backend.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin
from apr_backend.db.enums import Confidence, FeedbackStatus, IssueType, RiskLevel, RuleType, Severity, TaskStatus


def enum_column(enum_type: type, name: str):
    return Enum(enum_type, name=name, native_enum=False, validate_strings=True, values_callable=lambda values: [item.value for item in values])


class ReviewTask(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        CheckConstraint("length(diff_content) <= 50000", name="diff_content_max_50000"),
        Index("ix_review_tasks_demo_owner_created_at", "demo_owner", "created_at"),
    )

    pr_title: Mapped[str] = mapped_column(String(255), nullable=False)
    pr_description: Mapped[str | None] = mapped_column(Text)
    project_name: Mapped[str | None] = mapped_column(String(255))
    target_branch: Mapped[str | None] = mapped_column(String(255))
    developer_name: Mapped[str | None] = mapped_column(String(255))
    demo_owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # SENSITIVE: stores the full PR diff submitted by the user (capped at 50k chars)
    diff_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(enum_column(TaskStatus, "task_status"), nullable=False, default=TaskStatus.pending)
    risk_level: Mapped[RiskLevel | None] = mapped_column(enum_column(RiskLevel, "risk_level"))
    issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    report: Mapped["ReviewReport | None"] = relationship(back_populates="task", cascade="all, delete-orphan")
    issues: Mapped[list["ReviewIssue"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    feedback_entries: Mapped[list["IssueFeedback"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class ReviewReport(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_reports"

    task_id: Mapped[str] = mapped_column(ForeignKey("review_tasks.id"), nullable=False, unique=True, index=True)
    # SENSITIVE: contains AI-generated PR summary derived from submitted code
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel, "report_risk_level"), nullable=False)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    issue_stats: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # SENSITIVE: full structured AI output; stored for debugging, never exposed in logs
    raw_ai_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    task: Mapped[ReviewTask] = relationship(back_populates="report")
    issues: Mapped[list["ReviewIssue"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReviewIssue(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_issues"
    __table_args__ = (Index("ix_review_issues_task_severity", "task_id", "severity"),)

    task_id: Mapped[str] = mapped_column(ForeignKey("review_tasks.id"), nullable=False, index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("review_reports.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_type: Mapped[IssueType] = mapped_column(enum_column(IssueType, "issue_type"), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "severity"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    line_hint: Mapped[str | None] = mapped_column(String(255))
    code_snippet: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Confidence] = mapped_column(enum_column(Confidence, "confidence"), nullable=False)
    matched_rule_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    feedback_status: Mapped[FeedbackStatus] = mapped_column(
        enum_column(FeedbackStatus, "feedback_status"), nullable=False, default=FeedbackStatus.none
    )

    task: Mapped[ReviewTask] = relationship(back_populates="issues")
    report: Mapped[ReviewReport] = relationship(back_populates="issues")
    feedback_entries: Mapped[list["IssueFeedback"]] = relationship(back_populates="issue", cascade="all, delete-orphan")


class ReviewRule(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_rules"
    __table_args__ = (Index("ix_review_rules_enabled_type", "enabled", "rule_type"),)

    demo_owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(enum_column(RuleType, "rule_type"), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "rule_severity"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IssueFeedback(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "issue_feedback"
    __table_args__ = (Index("ix_issue_feedback_issue_created_at", "issue_id", "created_at"),)

    issue_id: Mapped[str] = mapped_column(ForeignKey("review_issues.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("review_tasks.id"), nullable=False, index=True)
    demo_owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    feedback_status: Mapped[FeedbackStatus] = mapped_column(enum_column(FeedbackStatus, "issue_feedback_status"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    issue: Mapped[ReviewIssue] = relationship(back_populates="feedback_entries")
    task: Mapped[ReviewTask] = relationship(back_populates="feedback_entries")
