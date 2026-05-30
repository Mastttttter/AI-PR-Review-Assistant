from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.core.settings import get_settings
from apr_backend.db.enums import (
    Confidence,
    FeedbackStatus,
    IssueType,
    RiskLevel,
    RuleType,
    Severity,
    TaskStatus,
)
from apr_backend.db.models import IssueFeedback, ReviewIssue, ReviewReport, ReviewRule, ReviewTask


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def db(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'edge.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Sess = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    yield Sess
    get_settings.cache_clear()


def _create_task(db, demo_owner: str = "edge-owner", **overrides) -> ReviewTask:
    with db() as session:
        task = ReviewTask(
            pr_title="Edge case task",
            demo_owner=demo_owner,
            diff_content="diff --git a/x b/x\n+line",
            status=TaskStatus.pending,
        )
        for k, v in overrides.items():
            setattr(task, k, v)
        session.add(task)
        session.commit()
        session.refresh(task)
        task_id = task.id
    with db() as session:
        return session.get(ReviewTask, task_id)


def _create_completed_task_with_report(db, demo_owner: str = "edge-owner") -> tuple[ReviewTask, ReviewReport]:
    with db() as session:
        task = ReviewTask(
            pr_title="Edge completed",
            demo_owner=demo_owner,
            diff_content="diff --git a/x b/x\n+line",
            status=TaskStatus.completed,
        )
        session.add(task)
        session.commit()
        report = ReviewReport(
            task_id=task.id,
            summary='{"purpose":"test"}',
            risk_level=RiskLevel.low,
            risk_reasons=["testing"],
            issue_stats={"total": 0, "high": 0, "medium": 0, "low": 0},
        )
        session.add(report)
        session.commit()
        task_id = task.id
        report_id = report.id
    with db() as session:
        return session.get(ReviewTask, task_id), session.get(ReviewReport, report_id)


class TestCascadeAndConstraints:
    def test_report_task_id_is_unique(self, db) -> None:
        task, _report = _create_completed_task_with_report(db)
        with db() as session:
            report2 = ReviewReport(
                task_id=task.id,
                summary="{}",
                risk_level=RiskLevel.medium,
                risk_reasons=[],
                issue_stats={},
            )
            session.add(report2)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

    def test_soft_deleted_task_preserves_deleted_at(self, db) -> None:
        task = _create_task(db)
        from datetime import UTC, datetime

        with db() as session:
            t = session.get(ReviewTask, task.id)
            t.status = TaskStatus.deleted
            t.deleted_at = datetime.now(UTC)
            session.commit()

        with db() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.deleted_at is not None
            assert reloaded.status == TaskStatus.deleted

    def test_multiple_issues_per_report(self, db) -> None:
        task, report = _create_completed_task_with_report(db)
        with db() as session:
            for i in range(5):
                session.add(
                    ReviewIssue(
                        task_id=task.id,
                        report_id=report.id,
                        title=f"Issue {i}",
                        issue_type=IssueType.maintainability,
                        severity=Severity.low,
                        description=f"Description {i}",
                        suggestion="Fix it.",
                        confidence=Confidence.medium,
                        matched_rule_ids=[],
                    )
                )
            session.commit()

        with db() as session:
            issues = list(
                session.scalars(
                    select(ReviewIssue).where(ReviewIssue.task_id == task.id)
                ).all()
            )
            assert len(issues) == 5

    def test_issue_feedback_cascade_delete_with_issue(self, db) -> None:
        task, report = _create_completed_task_with_report(db)
        with db() as session:
            issue = ReviewIssue(
                task_id=task.id,
                report_id=report.id,
                title="Deletable issue",
                issue_type=IssueType.maintainability,
                severity=Severity.low,
                description="Will be deleted.",
                suggestion="N/A",
                confidence=Confidence.low,
            )
            session.add(issue)
            session.commit()

            fb = IssueFeedback(
                issue_id=issue.id,
                task_id=task.id,
                demo_owner="edge-owner",
                feedback_status=FeedbackStatus.useful,
                comment="Good",
            )
            session.add(fb)
            session.commit()

            session.delete(issue)
            session.commit()

            remaining = list(
                session.scalars(
                    select(IssueFeedback).where(IssueFeedback.issue_id == issue.id)
                ).all()
            )
            assert len(remaining) == 0

    def test_rule_soft_deleted_excluded_from_queries(self, db) -> None:
        from datetime import UTC, datetime

        with db() as session:
            active = ReviewRule(
                demo_owner="edge-owner",
                name="Active rule",
                description="Should appear",
                rule_type=RuleType.style,
                severity=Severity.low,
                enabled=True,
            )
            deleted = ReviewRule(
                demo_owner="edge-owner",
                name="Deleted rule",
                description="Should not appear",
                rule_type=RuleType.style,
                severity=Severity.low,
                enabled=True,
                deleted_at=datetime.now(UTC),
            )
            session.add_all([active, deleted])
            session.commit()

            active_rules = list(
                session.scalars(
                    select(ReviewRule).where(
                        ReviewRule.demo_owner == "edge-owner",
                        ReviewRule.deleted_at.is_(None),
                    )
                ).all()
            )
            assert len(active_rules) == 1
            assert active_rules[0].name == "Active rule"


class TestNullableFields:
    def test_task_without_optional_fields(self, db) -> None:
        task = _create_task(db)
        assert task.pr_description is None
        assert task.project_name is None
        assert task.target_branch is None
        assert task.developer_name is None
        assert task.risk_level is None
        assert task.error_message is None
        assert task.deleted_at is None

    def test_issue_without_code_location(self, db) -> None:
        task, report = _create_completed_task_with_report(db)
        with db() as session:
            issue = ReviewIssue(
                task_id=task.id,
                report_id=report.id,
                title="No location",
                issue_type=IssueType.logic,
                severity=Severity.medium,
                description="No specific file.",
                suggestion="Review logic.",
                confidence=Confidence.medium,
            )
            session.add(issue)
            session.commit()
            issue_id = issue.id

        with db() as session:
            reloaded = session.get(ReviewIssue, issue_id)
            assert reloaded.file_path is None
            assert reloaded.line_hint is None
            assert reloaded.code_snippet is None

    def test_feedback_comment_can_be_null(self, db) -> None:
        task, report = _create_completed_task_with_report(db)
        with db() as session:
            issue = ReviewIssue(
                task_id=task.id,
                report_id=report.id,
                title="Feedback test",
                issue_type=IssueType.maintainability,
                severity=Severity.low,
                description="Test",
                suggestion="Fix.",
                confidence=Confidence.low,
            )
            session.add(issue)
            session.commit()

            fb = IssueFeedback(
                issue_id=issue.id,
                task_id=task.id,
                demo_owner="edge-owner",
                feedback_status=FeedbackStatus.useful,
                comment=None,
            )
            session.add(fb)
            session.commit()
            assert fb.comment is None


class TestEnumValidation:
    def test_valid_task_status_values_persist(self, db) -> None:
        for status in TaskStatus:
            task = _create_task(db, status=status)
            assert task.status == status

    def test_valid_risk_level_values_persist(self, db) -> None:
        for level in RiskLevel:
            task, report = _create_completed_task_with_report(db)
            with db() as session:
                r = session.get(ReviewReport, report.id)
                r.risk_level = level
                session.commit()
            with db() as session:
                assert session.get(ReviewReport, report.id).risk_level == level

    def test_all_issue_types_persist(self, db) -> None:
        task, report = _create_completed_task_with_report(db)
        with db() as session:
            for itype in IssueType:
                session.add(
                    ReviewIssue(
                        task_id=task.id,
                        report_id=report.id,
                        title=f"Issue type {itype.value}",
                        issue_type=itype,
                        severity=Severity.medium,
                        description="Test",
                        suggestion="Fix.",
                        confidence=Confidence.medium,
                    )
                )
            session.commit()

        with db() as session:
            count = len(
                list(
                    session.scalars(
                        select(ReviewIssue).where(ReviewIssue.task_id == task.id)
                    ).all()
                )
            )
            assert count == len(list(IssueType))
