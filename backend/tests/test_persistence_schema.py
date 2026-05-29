from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from apr_backend.core.settings import get_settings
from apr_backend.db.enums import Confidence, FeedbackStatus, IssueType, RiskLevel, RuleType, Severity, TaskStatus
from apr_backend.db.models import IssueFeedback, ReviewIssue, ReviewReport, ReviewRule, ReviewTask


def alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def migrated_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'schema.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    cfg = alembic_config(database_url)
    command.upgrade(cfg, "head")
    yield database_url
    get_settings.cache_clear()


def test_migration_up_and_down_on_clean_database(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    cfg = alembic_config(database_url)

    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    assert {
        "review_tasks",
        "review_reports",
        "review_issues",
        "review_rules",
        "issue_feedback",
    }.issubset(set(inspect(engine).get_table_names()))

    command.downgrade(cfg, "base")
    assert "review_tasks" not in set(inspect(engine).get_table_names())
    get_settings.cache_clear()


def test_models_persist_every_review_table(migrated_database) -> None:
    engine = create_engine(migrated_database)

    with Session(engine) as session:
        task = ReviewTask(
            pr_title="Add token refresh",
            pr_description="Refresh expired tokens before retrying requests.",
            project_name="user-center",
            target_branch="main",
            developer_name="Alice",
            demo_owner="demo-user",
            diff_content="diff --git a/auth.py b/auth.py\n+refresh_token()",
            status=TaskStatus.completed,
            risk_level=RiskLevel.high,
            issue_count=1,
        )
        report = ReviewReport(
            task=task,
            summary="Updates authentication token refresh behavior.",
            risk_level=RiskLevel.high,
            risk_reasons=["Authentication flow changed"],
            issue_stats={"total": 1, "high": 1, "medium": 0, "low": 0},
            raw_ai_result={"summary": {"purpose": "token refresh"}},
        )
        rule_id = str(uuid4())
        rule = ReviewRule(
            id=rule_id,
            demo_owner="demo-user",
            name="Auth changes need tests",
            description="Authentication changes require matching tests.",
            rule_type=RuleType.test,
            severity=Severity.medium,
            enabled=True,
        )
        issue = ReviewIssue(
            task=task,
            report=report,
            title="Missing authentication test",
            issue_type=IssueType.test_missing,
            severity=Severity.high,
            description="Token refresh changed without a regression test.",
            file_path="auth.py",
            line_hint="+refresh_token()",
            code_snippet="refresh_token()",
            suggestion="Add a regression test for expired token refresh.",
            confidence=Confidence.high,
            matched_rule_ids=[rule_id],
            feedback_status=FeedbackStatus.none,
        )
        feedback = IssueFeedback(
            issue=issue,
            task=task,
            demo_owner="demo-user",
            feedback_status=FeedbackStatus.useful,
            comment="Relevant finding.",
        )
        issue.feedback_status = feedback.feedback_status
        session.add_all([task, report, rule, issue, feedback])
        session.commit()

    with Session(engine) as session:
        saved_task = session.query(ReviewTask).filter_by(demo_owner="demo-user").one()
        saved_issue = session.query(ReviewIssue).filter_by(task_id=saved_task.id).one()
        saved_feedback = session.query(IssueFeedback).filter_by(issue_id=saved_issue.id).one()
        assert saved_task.status is TaskStatus.completed
        assert saved_task.risk_level is RiskLevel.high
        assert saved_issue.issue_type is IssueType.test_missing
        assert saved_issue.feedback_status is FeedbackStatus.useful
        assert saved_issue.matched_rule_ids == [session.query(ReviewRule).one().id]
        assert saved_feedback.comment == "Relevant finding."


def test_diff_content_accepts_50000_characters(migrated_database) -> None:
    engine = create_engine(migrated_database)
    with Session(engine) as session:
        session.add(
            ReviewTask(
                pr_title="Large diff",
                demo_owner="demo-user",
                diff_content="x" * 50000,
                status=TaskStatus.pending,
            )
        )
        session.commit()


def test_diff_content_rejects_more_than_50000_characters(migrated_database) -> None:
    engine = create_engine(migrated_database)
    with Session(engine) as session:
        session.add(
            ReviewTask(
                pr_title="Too large diff",
                demo_owner="demo-user",
                diff_content="x" * 50001,
                status=TaskStatus.pending,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_english_enum_value_is_rejected(migrated_database) -> None:
    engine = create_engine(migrated_database)
    with Session(engine) as session:
        session.add(
            ReviewTask(
                pr_title="Invalid status",
                demo_owner="demo-user",
                diff_content="diff",
                status="queued",
            )
        )
        with pytest.raises(StatementError):
            session.commit()
