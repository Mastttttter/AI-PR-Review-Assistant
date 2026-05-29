from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.review_tasks import get_db
from apr_backend.core.settings import get_settings
from apr_backend.db.enums import RiskLevel, TaskStatus
from apr_backend.db.models import ReviewTask
from apr_backend.main import create_app


def alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    get_settings.cache_clear()


@pytest.fixture
def enqueued_jobs(monkeypatch) -> list[str]:
    jobs: list[str] = []

    def fake_enqueue(task_id: str) -> str:
        jobs.append(task_id)
        return f"job-{task_id}"

    monkeypatch.setattr("apr_backend.api.review_tasks.enqueue_review_job", fake_enqueue)
    return jobs


@pytest.fixture
def client(session_factory, enqueued_jobs) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


OWNER_HEADER = {"X-Demo-Owner": "owner-a"}


def create_payload(**overrides):
    payload = {
        "pr_title": "Add token refresh",
        "pr_description": "Refresh expired tokens before retrying requests.",
        "project_name": "user-center",
        "target_branch": "main",
        "developer_name": "Alice",
        "diff_content": "diff --git a/auth.py b/auth.py\n+refresh_token()",
    }
    payload.update(overrides)
    return payload


def test_create_review_task_validates_stores_and_enqueues(client, session_factory, enqueued_jobs) -> None:
    response = client.post("/api/review-tasks", json=create_payload(), headers=OWNER_HEADER)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert enqueued_jobs == [body["task_id"]]

    with session_factory() as session:
        task = session.get(ReviewTask, body["task_id"])
        assert task is not None
        assert task.pr_title == "Add token refresh"
        assert task.demo_owner == "owner-a"
        assert task.diff_content.startswith("diff --git")


def test_create_review_task_requires_owner_title_and_diff(client) -> None:
    assert client.post("/api/review-tasks", json=create_payload()).status_code == 422
    assert client.post("/api/review-tasks", json=create_payload(pr_title=" "), headers=OWNER_HEADER).status_code == 422
    assert client.post("/api/review-tasks", json=create_payload(diff_content=""), headers=OWNER_HEADER).status_code == 422


def test_create_review_task_rejects_diff_above_50000_characters(client) -> None:
    response = client.post("/api/review-tasks", json=create_payload(diff_content="x" * 50001), headers=OWNER_HEADER)

    assert response.status_code == 422


def test_list_filters_active_tasks_by_owner_status_and_project(client, session_factory) -> None:
    with session_factory() as session:
        session.add_all(
            [
                ReviewTask(pr_title="Active", demo_owner="owner-a", project_name="api", diff_content="diff", status=TaskStatus.pending),
                ReviewTask(pr_title="Done", demo_owner="owner-a", project_name="web", diff_content="diff", status=TaskStatus.completed),
                ReviewTask(pr_title="Other owner", demo_owner="owner-b", project_name="api", diff_content="diff", status=TaskStatus.pending),
                ReviewTask(
                    pr_title="Deleted",
                    demo_owner="owner-a",
                    project_name="api",
                    diff_content="diff",
                    status=TaskStatus.deleted,
                    deleted_at=datetime.now(UTC),
                ),
            ]
        )
        session.commit()

    response = client.get("/api/review-tasks?status=pending&project_name=api", headers=OWNER_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert [task["pr_title"] for task in body] == ["Active"]


def test_detail_returns_owned_active_task(client, session_factory) -> None:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="Detail",
            demo_owner="owner-a",
            diff_content="diff",
            status=TaskStatus.completed,
            risk_level=RiskLevel.medium,
            issue_count=2,
        )
        session.add(task)
        session.commit()
        task_id = task.id

    response = client.get(f"/api/review-tasks/{task_id}", headers=OWNER_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == task_id
    assert body["risk_level"] == "medium"
    assert body["diff_content"] == "diff"


def test_detail_hides_other_owner_and_deleted_tasks(client, session_factory) -> None:
    with session_factory() as session:
        other = ReviewTask(pr_title="Other", demo_owner="owner-b", diff_content="diff", status=TaskStatus.pending)
        deleted = ReviewTask(
            pr_title="Deleted",
            demo_owner="owner-a",
            diff_content="diff",
            status=TaskStatus.deleted,
            deleted_at=datetime.now(UTC),
        )
        session.add_all([other, deleted])
        session.commit()
        other_id = other.id
        deleted_id = deleted.id

    assert client.get(f"/api/review-tasks/{other_id}", headers=OWNER_HEADER).status_code == 404
    assert client.get(f"/api/review-tasks/{deleted_id}", headers=OWNER_HEADER).status_code == 404


def test_soft_delete_marks_task_and_excludes_from_active_records(client, session_factory) -> None:
    with session_factory() as session:
        task = ReviewTask(pr_title="Delete me", demo_owner="owner-a", diff_content="diff", status=TaskStatus.pending)
        session.add(task)
        session.commit()
        task_id = task.id

    delete_response = client.delete(f"/api/review-tasks/{task_id}", headers=OWNER_HEADER)
    list_response = client.get("/api/review-tasks", headers=OWNER_HEADER)
    detail_response = client.get(f"/api/review-tasks/{task_id}", headers=OWNER_HEADER)

    assert delete_response.status_code == 204
    assert list_response.json() == []
    assert detail_response.status_code == 404
    with session_factory() as session:
        task = session.get(ReviewTask, task_id)
        assert task.status is TaskStatus.deleted
        assert task.deleted_at is not None


def test_rerun_resets_task_and_enqueues_review_job(client, session_factory, enqueued_jobs) -> None:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="Rerun me",
            demo_owner="owner-a",
            diff_content="diff",
            status=TaskStatus.failed,
            risk_level=RiskLevel.high,
            issue_count=3,
            error_message="LLM failed",
        )
        session.add(task)
        session.commit()
        task_id = task.id

    response = client.post(f"/api/review-tasks/{task_id}/rerun", headers=OWNER_HEADER)

    assert response.status_code == 200
    assert response.json() == {"task_id": task_id, "status": "pending"}
    assert enqueued_jobs == [task_id]
    with session_factory() as session:
        task = session.scalar(select(ReviewTask).where(ReviewTask.id == task_id))
        assert task.status is TaskStatus.pending
        assert task.risk_level is None
        assert task.issue_count == 0
        assert task.error_message is None


def test_rerun_rejects_deleted_task(client, session_factory, enqueued_jobs) -> None:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="Deleted",
            demo_owner="owner-a",
            diff_content="diff",
            status=TaskStatus.deleted,
            deleted_at=datetime.now(UTC),
        )
        session.add(task)
        session.commit()
        task_id = task.id

    response = client.post(f"/api/review-tasks/{task_id}/rerun", headers=OWNER_HEADER)

    assert response.status_code == 404
    assert enqueued_jobs == []
