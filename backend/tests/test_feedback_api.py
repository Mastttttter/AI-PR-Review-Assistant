from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.issue_feedback import get_db
from apr_backend.core.settings import get_settings
from apr_backend.db.enums import (
    Confidence,
    FeedbackStatus,
    IssueType,
    RiskLevel,
    Severity,
    TaskStatus,
)
from apr_backend.db.models import IssueFeedback, ReviewIssue, ReviewReport, ReviewTask
from apr_backend.main import create_app


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'feedback.db'}"
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


def _create_issue(session_factory) -> str:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="T", demo_owner="owner-a", diff_content="diff",
            status=TaskStatus.completed, risk_level=RiskLevel.low,
        )
        session.add(task)
        session.commit()

        report = ReviewReport(
            task_id=task.id, summary="{}", risk_level=RiskLevel.low, risk_reasons=[],
            issue_stats={"total": 1, "high": 0, "medium": 0, "low": 1},
        )
        session.add(report)
        session.commit()

        issue = ReviewIssue(
            task_id=task.id, report_id=report.id,
            title="Test issue", issue_type=IssueType.logic, severity=Severity.low,
            description="A test issue.", suggestion="Fix it.",
            confidence=Confidence.high, feedback_status=FeedbackStatus.none,
        )
        session.add(issue)
        session.commit()
        return issue.id


class TestEachStatus:
    @pytest.mark.parametrize("status_val", ["useful", "useless", "false_positive", "adopted", "ignored"])
    def test_each_valid_status_accepted(self, client, session_factory, status_val) -> None:
        iid = _create_issue(session_factory)
        response = client.patch(
            f"/api/review-issues/{iid}/feedback",
            json={"feedback_status": status_val},
            headers=OWNER,
        )
        assert response.status_code == 200
        assert response.json()["feedback_status"] == status_val

    @pytest.mark.parametrize("status_val", ["useful", "useless", "false_positive", "adopted", "ignored"])
    def test_issue_feedback_status_updated(self, client, session_factory, status_val) -> None:
        iid = _create_issue(session_factory)
        client.patch(f"/api/review-issues/{iid}/feedback", json={"feedback_status": status_val}, headers=OWNER)

        with session_factory() as session:
            issue = session.get(ReviewIssue, iid)
            assert issue.feedback_status.value == status_val


class TestComment:
    def test_optional_comment_is_stored(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        response = client.patch(
            f"/api/review-issues/{iid}/feedback",
            json={"feedback_status": "useful", "comment": "Good catch!"},
            headers=OWNER,
        )
        assert response.status_code == 200
        assert response.json()["comment"] == "Good catch!"

    def test_comment_can_be_null(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        response = client.patch(
            f"/api/review-issues/{iid}/feedback",
            json={"feedback_status": "useful"},
            headers=OWNER,
        )
        assert response.status_code == 200
        assert response.json()["comment"] is None


class TestHistory:
    def test_feedback_record_is_persisted(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        client.patch(f"/api/review-issues/{iid}/feedback", json={"feedback_status": "useful"}, headers=OWNER)

        with session_factory() as session:
            records = list(session.scalars(
                select(IssueFeedback).where(IssueFeedback.issue_id == iid)
            ).all())
            assert len(records) >= 1
            assert records[-1].feedback_status == FeedbackStatus.useful


class TestRepeatUpdate:
    def test_latest_feedback_overwrites_previous(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        client.patch(f"/api/review-issues/{iid}/feedback", json={"feedback_status": "useful"}, headers=OWNER)
        client.patch(f"/api/review-issues/{iid}/feedback", json={"feedback_status": "ignored"}, headers=OWNER)

        with session_factory() as session:
            issue = session.get(ReviewIssue, iid)
            assert issue.feedback_status == FeedbackStatus.ignored


class TestErrors:
    def test_invalid_status_rejected(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        response = client.patch(
            f"/api/review-issues/{iid}/feedback",
            json={"feedback_status": "bogus"},
            headers=OWNER,
        )
        assert response.status_code == 422

    def test_missing_issue_returns_404(self, client) -> None:
        response = client.patch(
            "/api/review-issues/nonexistent-id/feedback",
            json={"feedback_status": "useful"},
            headers=OWNER,
        )
        assert response.status_code == 404

    def test_missing_owner_header_rejected(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        response = client.patch(
            f"/api/review-issues/{iid}/feedback",
            json={"feedback_status": "useful"},
        )
        assert response.status_code == 422


class TestReportReflectsFeedback:
    def test_feedback_status_on_issue_is_updated_for_report(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        client.patch(f"/api/review-issues/{iid}/feedback", json={"feedback_status": "adopted"}, headers=OWNER)

        with session_factory() as session:
            issue = session.get(ReviewIssue, iid)
            assert issue.feedback_status == FeedbackStatus.adopted

    def test_ai_report_content_unchanged_by_feedback(self, client, session_factory) -> None:
        iid = _create_issue(session_factory)
        with session_factory() as session:
            original = session.get(ReviewIssue, iid)
            original_desc = original.description
            original_suggestion = original.suggestion

        client.patch(f"/api/review-issues/{iid}/feedback", json={"feedback_status": "false_positive"}, headers=OWNER)

        with session_factory() as session:
            updated = session.get(ReviewIssue, iid)
            assert updated.description == original_desc
            assert updated.suggestion == original_suggestion
            assert updated.feedback_status == FeedbackStatus.false_positive
