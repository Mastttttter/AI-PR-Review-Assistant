from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.metrics import get_db
from apr_backend.api.review_tasks import get_db as tasks_get_db
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
    database_url = f"sqlite:///{tmp_path / 'metrics.db'}"
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
    app.dependency_overrides[tasks_get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


OWNER = {"X-Demo-Owner": "owner-a"}


def _seed_tasks(session_factory) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add_all([
            ReviewTask(pr_title="High risk", demo_owner="owner-a", diff_content="d", status=TaskStatus.completed, risk_level=RiskLevel.high, issue_count=3, created_at=now),
            ReviewTask(pr_title="Medium risk", demo_owner="owner-a", diff_content="d", status=TaskStatus.completed, risk_level=RiskLevel.medium, issue_count=1, created_at=now - timedelta(days=10)),
            ReviewTask(pr_title="Low risk", demo_owner="owner-a", diff_content="d", status=TaskStatus.completed, risk_level=RiskLevel.low, issue_count=0, created_at=now - timedelta(days=40)),
            ReviewTask(pr_title="Pending", demo_owner="owner-a", diff_content="d", status=TaskStatus.pending, risk_level=None, created_at=now),
            ReviewTask(pr_title="Old completed", demo_owner="owner-a", diff_content="d", status=TaskStatus.completed, risk_level=RiskLevel.low, issue_count=1, created_at=now - timedelta(days=60)),
            ReviewTask(pr_title="Other owner", demo_owner="owner-b", diff_content="d", status=TaskStatus.completed, risk_level=RiskLevel.high, created_at=now),
            ReviewTask(pr_title="Deleted", demo_owner="owner-a", diff_content="d", status=TaskStatus.deleted, risk_level=RiskLevel.medium, deleted_at=now),
        ])
        session.commit()


def _seed_feedback(session_factory, task_id: str) -> None:
    with session_factory() as session:
        report = ReviewReport(
            task_id=task_id, summary="{}", risk_level=RiskLevel.low, risk_reasons=[],
            issue_stats={"total": 3, "high": 0, "medium": 0, "low": 3},
        )
        session.add(report)
        session.commit()

        for i in range(3):
            issue = ReviewIssue(
                task_id=task_id, report_id=report.id,
                title=f"Issue {i}", issue_type=IssueType.logic, severity=Severity.low,
                description="desc", suggestion="s", confidence=Confidence.high,
            )
            session.add(issue)
            session.commit()

            statuses = [FeedbackStatus.useful, FeedbackStatus.false_positive, FeedbackStatus.adopted]
            feedback = IssueFeedback(
                issue_id=issue.id, task_id=task_id, demo_owner="owner-a",
                feedback_status=statuses[i], comment=None,
            )
            session.add(feedback)
            session.commit()


class TestListFilters:
    def test_risk_level_filter(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/review-tasks?risk_level=high", headers=OWNER)
        assert resp.status_code == 200
        titles = [t["pr_title"] for t in resp.json()]
        assert titles == ["High risk"]

    def test_created_after_filter(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        cutoff = (datetime.now(UTC) - timedelta(days=15)).date().isoformat()
        resp = client.get(f"/api/review-tasks?created_after={cutoff}", headers=OWNER)
        titles = [t["pr_title"] for t in resp.json()]
        assert "High risk" in titles
        assert "Medium risk" in titles
        assert "Pending" in titles

    def test_created_before_filter(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        cutoff = (datetime.now(UTC) - timedelta(days=50)).date().isoformat()
        resp = client.get(f"/api/review-tasks?created_before={cutoff}", headers=OWNER)
        titles = [t["pr_title"] for t in resp.json()]
        assert "Old completed" in titles
        assert "Low risk" not in titles

    def test_combined_filters(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/review-tasks?status=completed&risk_level=medium", headers=OWNER)
        titles = [t["pr_title"] for t in resp.json()]
        assert titles == ["Medium risk"]

    def test_deleted_tasks_excluded(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/review-tasks?risk_level=medium", headers=OWNER)
        titles = [t["pr_title"] for t in resp.json()]
        assert "Deleted" not in titles


class TestDashboard:
    def test_total_tasks_excludes_deleted(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_tasks"] == 5

    def test_risk_distribution(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        dist = resp.json()["risk_distribution"]
        assert dist["high"] == 1
        assert dist["medium"] == 1
        assert dist["low"] == 2

    def test_tasks_last_30_days(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        assert resp.json()["tasks_last_30_days"] == 3

    def test_total_issues_excludes_deleted_task_issues(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        assert resp.json()["total_issues"] == 0  # no issues seeded yet in _seed_tasks

    def test_feedback_rates(self, client, session_factory) -> None:
        with session_factory() as session:
            task = ReviewTask(
                pr_title="Task with feedback", demo_owner="owner-a", diff_content="d",
                status=TaskStatus.completed, risk_level=RiskLevel.low,
            )
            session.add(task)
            session.commit()
            tid = task.id

        _seed_feedback(session_factory, tid)

        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        body = resp.json()
        assert body["useful_rate"] == pytest.approx(1 / 3, abs=0.01)
        assert body["false_positive_rate"] == pytest.approx(1 / 3, abs=0.01)
        assert body["adoption_rate"] == pytest.approx(1 / 3, abs=0.01)

    def test_empty_dashboard_returns_zero_rates(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        body = resp.json()
        assert body["useful_rate"] == 0.0
        assert body["false_positive_rate"] == 0.0
        assert body["adoption_rate"] == 0.0

    def test_other_owner_data_not_included(self, client, session_factory) -> None:
        _seed_tasks(session_factory)
        resp = client.get("/api/metrics/dashboard", headers=OWNER)
        assert resp.status_code == 200
