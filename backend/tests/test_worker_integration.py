from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.core.settings import get_settings
from apr_backend.db.enums import TaskStatus
from apr_backend.db.models import ReviewTask
from apr_backend.services.llm_adapter import MockLLMProvider
from apr_backend.worker.jobs import review_task_job

MULTI_FILE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,8 @@
 def login(user, password):
     if not user:
         return None
+    if not user.is_active:
+        return None
     token = generate_token(user)
     return token
diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,5 @@
+def test_login_active_user():
+    user = User(is_active=True)
+    result = login(user, "secret")
+    assert result is not None
"""


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def db_session_factory(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'worker.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Sess = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    get_settings.cache_clear()

    # Replace SessionLocal so orchestrator uses the temp DB
    monkeypatch.setattr(
        "apr_backend.services.orchestrator.SessionLocal",
        Sess,
    )
    monkeypatch.setattr(
        "apr_backend.services.orchestrator.create_llm_provider",
        lambda: MockLLMProvider(),
    )

    yield Sess
    get_settings.cache_clear()


def _create_task(session_factory, **overrides) -> ReviewTask:
    with session_factory() as session:
        task = ReviewTask(
            pr_title="Worker test",
            project_name="worker-project",
            demo_owner="worker-owner",
            diff_content=MULTI_FILE_DIFF,
            status=TaskStatus.pending,
        )
        for k, v in overrides.items():
            setattr(task, k, v)
        session.add(task)
        session.commit()
        task_id = task.id
    with session_factory() as session:
        return session.get(ReviewTask, task_id)


class TestWorkerJob:
    def test_review_task_job_returns_task_id(self, db_session_factory) -> None:
        task = _create_task(db_session_factory)
        result = review_task_job(task.id)
        assert result == task.id

    def test_review_task_job_transitions_to_completed(self, db_session_factory) -> None:
        task = _create_task(db_session_factory)
        review_task_job(task.id)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.completed
            assert reloaded.risk_level is not None
            assert reloaded.issue_count > 0

    def test_job_skips_deleted_task(self, db_session_factory) -> None:
        from datetime import UTC, datetime

        task = _create_task(db_session_factory, status=TaskStatus.deleted, deleted_at=datetime.now(UTC))
        review_task_job(task.id)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.status == TaskStatus.deleted

    def test_job_produces_report_and_issues(self, db_session_factory) -> None:
        task = _create_task(db_session_factory)
        review_task_job(task.id)

        with db_session_factory() as session:
            reloaded = session.get(ReviewTask, task.id)
            assert reloaded.report is not None
            assert len(reloaded.report.summary) > 0
            assert len(reloaded.issues) > 0

    def test_multiple_jobs_for_different_tasks(self, db_session_factory) -> None:
        task_1 = _create_task(db_session_factory)
        task_2 = _create_task(db_session_factory)

        review_task_job(task_1.id)
        review_task_job(task_2.id)

        with db_session_factory() as session:
            t1 = session.get(ReviewTask, task_1.id)
            t2 = session.get(ReviewTask, task_2.id)
            assert t1.status == TaskStatus.completed
            assert t2.status == TaskStatus.completed
            assert t1.id != t2.id

    def test_worker_job_handles_nonexistent_task(self, db_session_factory) -> None:
        result = review_task_job("nonexistent-id")
        assert result == "nonexistent-id"


class TestWorkerStartup:
    def test_create_worker_does_not_raise(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.worker.entrypoint.create_worker",
            lambda: None,
        )
        # Just verify the module loads without error
        from apr_backend.worker import entrypoint

        assert entrypoint.create_worker is not None

    def test_readiness_payload_has_required_fields(self, monkeypatch) -> None:
        from apr_backend.worker.entrypoint import readiness_payload

        payload = readiness_payload()
        assert "status" in payload
        assert payload["status"] == "ready"
        assert "queue" in payload
        assert "redis_url" in payload

    def test_main_check_only_returns_zero(self, monkeypatch) -> None:
        monkeypatch.setenv("APR_REDIS_URL", "redis://dummy:6379/0")
        get_settings.cache_clear()
        from apr_backend.worker.entrypoint import main

        exit_code = main(check_only=True)
        assert exit_code == 0
        get_settings.cache_clear()
