from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.review_tasks import get_db
from apr_backend.core.settings import get_settings
from apr_backend.db.enums import (
    Confidence,
    FeedbackStatus,
    IssueType,
    RiskLevel,
    Severity,
    TaskStatus,
)
from apr_backend.db.models import ReviewIssue, ReviewReport, ReviewTask
from apr_backend.main import create_app


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'report.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    get_settings.cache_clear()


@pytest.fixture
def client(session_factory) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


OWNER = {"X-Demo-Owner": "owner-a"}

REPORT_SUMMARY = json.dumps({
    "purpose": "Add token refresh logic.",
    "changed_modules": ["auth"],
    "key_files": ["src/auth.py"],
    "business_impact": "Users stay logged in longer.",
    "test_or_security_notes": "Tests included.",
}, ensure_ascii=False)


def _create_completed_task(session_factory) -> str:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="Add token refresh",
            pr_description="Refresh expired tokens.",
            project_name="user-center",
            target_branch="main",
            developer_name="Alice",
            demo_owner="owner-a",
            diff_content="diff --git a/x b/x\n+1",
            status=TaskStatus.completed,
            risk_level=RiskLevel.medium,
            issue_count=3,
        )
        session.add(task)
        session.commit()
        tid = task.id

        report = ReviewReport(
            task_id=tid,
            summary=REPORT_SUMMARY,
            risk_level=RiskLevel.medium,
            risk_reasons=["Modifies auth logic."],
            issue_stats={"total": 3, "high": 1, "medium": 1, "low": 1},
        )
        session.add(report)
        session.commit()

        issues = [
            ReviewIssue(
                task_id=tid, report_id=report.id,
                title="High severity issue", issue_type=IssueType.security, severity=Severity.high,
                description="Security gap.", suggestion="Fix it.", confidence=Confidence.high,
                file_path="src/auth.py", line_hint="line 10", code_snippet="login()",
                matched_rule_ids=[], feedback_status=FeedbackStatus.none,
            ),
            ReviewIssue(
                task_id=tid, report_id=report.id,
                title="Low severity issue", issue_type=IssueType.maintainability, severity=Severity.low,
                description="Minor style issue.", suggestion="Clean up.", confidence=Confidence.high,
                matched_rule_ids=["rule-1"], feedback_status=FeedbackStatus.useful,
            ),
            ReviewIssue(
                task_id=tid, report_id=report.id,
                title="Medium severity issue", issue_type=IssueType.performance, severity=Severity.medium,
                description="Performance concern.", suggestion="Optimize.", confidence=Confidence.medium,
                matched_rule_ids=[], feedback_status=FeedbackStatus.adopted,
            ),
        ]
        session.add_all(issues)
        session.commit()
        return tid


class TestCompletedReport:
    def test_returns_report_with_pr_basics(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["pr_title"] == "Add token refresh"
        assert body["pr_description"] == "Refresh expired tokens."
        assert body["project_name"] == "user-center"
        assert body["status"] == "completed"

    def test_summary_and_risk_are_populated(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        body = response.json()
        assert body["summary"] == REPORT_SUMMARY
        assert body["risk_level"] == "medium"
        assert body["risk_reasons"] == ["Modifies auth logic."]

    def test_issues_sorted_by_severity_high_first(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        body = response.json()
        severities = [i["severity"] for i in body["issues"]]
        assert severities == ["high", "medium", "low"]

    def test_issue_stats_are_correct(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        stats = response.json()["issue_stats"]
        assert stats["total"] == 3
        assert stats["high"] == 1
        assert stats["medium"] == 1
        assert stats["low"] == 1

    def test_issues_contain_all_prd_fields(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        issue = response.json()["issues"][0]
        assert "id" in issue
        assert "title" in issue
        assert "issue_type" in issue
        assert "severity" in issue
        assert "description" in issue
        assert "suggestion" in issue
        assert "confidence" in issue
        assert "file_path" in issue
        assert "line_hint" in issue
        assert "code_snippet" in issue
        assert "matched_rule_ids" in issue
        assert "feedback_status" in issue

    def test_feedback_status_reflected(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        feedbacks = {i["title"]: i["feedback_status"] for i in response.json()["issues"]}
        assert feedbacks["Low severity issue"] == "useful"
        assert feedbacks["Medium severity issue"] == "adopted"
        assert feedbacks["High severity issue"] == "none"


class TestPendingTask:
    def test_pending_task_returns_null_summary(self, client, session_factory) -> None:
        with session_factory() as session:
            task = ReviewTask(pr_title="Pending", demo_owner="owner-a", diff_content="diff", status=TaskStatus.pending)
            session.add(task)
            session.commit()
            tid = task.id

        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["summary"] is None
        assert body["risk_reasons"] == []
        assert body["issues"] == []


class TestFailedTask:
    def test_failed_task_returns_error_message(self, client, session_factory) -> None:
        with session_factory() as session:
            task = ReviewTask(
                pr_title="Failed", demo_owner="owner-a", diff_content="diff",
                status=TaskStatus.failed, error_message="LLM call failed.",
            )
            session.add(task)
            session.commit()
            tid = task.id

        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["error_message"] == "LLM call failed."


class TestAccessControl:
    def test_other_owner_cannot_access_report(self, client, session_factory) -> None:
        tid = _create_completed_task(session_factory)
        response = client.get(f"/api/review-tasks/{tid}/report", headers={"X-Demo-Owner": "owner-b"})
        assert response.status_code == 404

    def test_deleted_task_report_returns_404(self, client, session_factory) -> None:
        with session_factory() as session:
            task = ReviewTask(
                pr_title="Deleted", demo_owner="owner-a", diff_content="diff",
                status=TaskStatus.deleted, deleted_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            session.add(task)
            session.commit()
            tid = task.id

        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)
        assert response.status_code == 404


class TestEmptyIssues:
    def test_empty_issue_list_returns_empty_array(self, client, session_factory) -> None:
        with session_factory() as session:
            task = ReviewTask(
                pr_title="Clean", demo_owner="owner-a", diff_content="diff",
                status=TaskStatus.completed, risk_level=RiskLevel.low,
            )
            session.add(task)
            session.commit()
            tid = task.id

            report = ReviewReport(
                task_id=tid, summary="{}", risk_level=RiskLevel.low, risk_reasons=[],
                issue_stats={"total": 0, "high": 0, "medium": 0, "low": 0},
            )
            session.add(report)
            session.commit()

        response = client.get(f"/api/review-tasks/{tid}/report", headers=OWNER)
        assert response.status_code == 200
        assert response.json()["issues"] == []
        assert response.json()["risk_level"] == "low"
