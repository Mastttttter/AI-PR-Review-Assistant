from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.review_tasks import get_db
from apr_backend.core.settings import get_settings
from apr_backend.db.enums import RiskLevel, Severity, TaskStatus
from apr_backend.db.models import ReviewReport, ReviewTask
from apr_backend.main import create_app
from apr_backend.services.llm_adapter import MockLLMProvider
from apr_backend.services.orchestrator import run_review_orchestrator

MINIMAL_DIFF = """\
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,5 @@
 def parse(data):
-    return json.loads(data)
+    if not data:
+        return {}
+    return json.loads(data.strip())
"""


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def smoke_db(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'smoke.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Sess = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    yield Sess
    get_settings.cache_clear()


@pytest.fixture
def smoke_client(smoke_db, monkeypatch):
    monkeypatch.setattr(
        "apr_backend.services.orchestrator.create_llm_provider",
        lambda: MockLLMProvider(),
    )

    app = create_app()

    def override_get_db():
        with smoke_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


class TestEndToEndCreateReviewToReport:
    """Smoke test: create a review task, run the orchestrator, retrieve the report."""

    def test_create_task_returns_pending(self, smoke_client) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "E2E smoke test", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["task_id"]
        assert body["status"] == "pending"

    def test_full_create_orchestrate_retrieve_loop(self, smoke_client, smoke_db) -> None:
        # Step 1: Create task via API
        resp = smoke_client.post(
            "/api/review-tasks",
            json={
                "pr_title": "E2E full loop",
                "pr_description": "Smoke test diff",
                "project_name": "smoke-project",
                "target_branch": "main",
                "developer_name": "tester",
                "diff_content": MINIMAL_DIFF,
            },
            headers={"X-Demo-Owner": "smoke"},
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]
        assert resp.json()["status"] == "pending"

        # Step 2: Run orchestrator directly (bypassing Redis queue)
        run_review_orchestrator(task_id, db_factory=smoke_db)

        # Step 3: Verify task is completed
        with smoke_db() as session:
            task = session.get(ReviewTask, task_id)
            assert task.status == TaskStatus.completed
            assert task.risk_level is not None
            assert task.issue_count > 0

        # Step 4: Retrieve report via API
        report_resp = smoke_client.get(
            f"/api/review-tasks/{task_id}/report",
            headers={"X-Demo-Owner": "smoke"},
        )
        assert report_resp.status_code == 200
        report = report_resp.json()

        # Step 5: Verify report structure
        assert report["id"]
        assert report["task"]["id"] == task_id
        assert report["task"]["pr_title"] == "E2E full loop"
        assert report["task"]["status"] == "completed"

        # Summary
        assert report["summary"] is not None
        assert "purpose" in report["summary"]

        # Risk
        assert report["risk"]["level"] in ("low", "medium", "high")
        assert isinstance(report["risk"]["reasons"], list)
        assert len(report["risk"]["reasons"]) > 0

        # Issue stats
        assert report["issue_stats"]["total"] > 0
        assert report["issue_stats"]["total"] == (
            report["issue_stats"]["high"] + report["issue_stats"]["medium"] + report["issue_stats"]["low"]
        )

        # Issues
        assert len(report["issues"]) > 0
        for issue in report["issues"]:
            assert issue["id"]
            assert issue["title"]
            assert issue["type"] in (
                "logic", "exception", "security", "performance",
                "maintainability", "test_missing", "rule_violation",
            )
            assert issue["severity"] in ("low", "medium", "high")
            assert issue["description"]
            assert issue["suggestion"]
            assert issue["confidence"] in ("low", "medium", "high")
            assert isinstance(issue["matched_rule_ids"], list)
            assert isinstance(issue["location"], dict)
            assert "file_path" in issue["location"]
            assert issue["feedback_status"] == "none"

    def test_task_list_shows_completed_task(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Listable", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]
        run_review_orchestrator(task_id, db_factory=smoke_db)

        listing = smoke_client.get("/api/review-tasks", headers={"X-Demo-Owner": "smoke"})
        assert listing.status_code == 200
        tasks = listing.json()
        assert len(tasks) == 1
        assert tasks[0]["id"] == task_id
        assert tasks[0]["risk_level"] is not None

    def test_report_with_rules_includes_matched_rule_ids(self, smoke_client, smoke_db) -> None:
        # Create a banned-content rule
        rules_resp = smoke_client.post(
            "/api/review-rules",
            json={
                "name": "No debugger statements",
                "description": "Prevents debugger; in code.",
                "rule_type": "style",
                "severity": "low",
            },
            headers={"X-Demo-Owner": "smoke"},
        )
        assert rules_resp.status_code == 201
        rule_id = rules_resp.json()["id"]

        # Diff with debugger statement to trigger rule
        diff_with_banned = """\
diff --git a/src/app.ts b/src/app.ts
--- a/src/app.ts
+++ b/src/app.ts
@@ -1,3 +1,4 @@
 function init() {
+  debugger;
   console.log("start");
 }
"""

        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Rule match test", "diff_content": diff_with_banned},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]
        run_review_orchestrator(task_id, db_factory=smoke_db)

        report_resp = smoke_client.get(
            f"/api/review-tasks/{task_id}/report",
            headers={"X-Demo-Owner": "smoke"},
        )
        report = report_resp.json()
        assert report["issue_stats"]["rule_hits"] > 0

    def test_issues_are_sorted_by_severity(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Severity sort", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]
        run_review_orchestrator(task_id, db_factory=smoke_db)

        report_resp = smoke_client.get(
            f"/api/review-tasks/{task_id}/report",
            headers={"X-Demo-Owner": "smoke"},
        )
        issues = report_resp.json()["issues"]
        if len(issues) > 1:
            sev_order = {"high": 0, "medium": 1, "low": 2}
            for i in range(len(issues) - 1):
                current = sev_order.get(issues[i]["severity"], 99)
                nxt = sev_order.get(issues[i + 1]["severity"], 99)
                assert current <= nxt, f"Issues not sorted: {issues[i]['severity']} before {issues[i+1]['severity']}"

    def test_deleted_task_not_in_list(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "To be deleted", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]

        smoke_client.delete(f"/api/review-tasks/{task_id}", headers={"X-Demo-Owner": "smoke"})

        listing = smoke_client.get("/api/review-tasks", headers={"X-Demo-Owner": "smoke"})
        assert listing.status_code == 200
        assert len(listing.json()) == 0

    def test_deleted_task_report_returns_404(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Del report", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]
        run_review_orchestrator(task_id, db_factory=smoke_db)

        smoke_client.delete(f"/api/review-tasks/{task_id}", headers={"X-Demo-Owner": "smoke"})

        report_resp = smoke_client.get(
            f"/api/review-tasks/{task_id}/report",
            headers={"X-Demo-Owner": "smoke"},
        )
        assert report_resp.status_code == 404

    def test_pending_task_report_has_null_summary(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Pending report", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]

        report_resp = smoke_client.get(
            f"/api/review-tasks/{task_id}/report",
            headers={"X-Demo-Owner": "smoke"},
        )
        assert report_resp.status_code == 200
        report = report_resp.json()
        assert report["summary"] is None
        assert report["issue_stats"]["total"] == 0

    def test_different_owner_cannot_access_report(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Owner task", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "owner-a"},
        )
        task_id = resp.json()["task_id"]
        run_review_orchestrator(task_id, db_factory=smoke_db)

        report_resp = smoke_client.get(
            f"/api/review-tasks/{task_id}/report",
            headers={"X-Demo-Owner": "owner-b"},
        )
        assert report_resp.status_code == 404

    def test_metrics_reflect_task_and_issues(self, smoke_client, smoke_db) -> None:
        resp = smoke_client.post(
            "/api/review-tasks",
            json={"pr_title": "Metrics smoke", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "smoke"},
        )
        task_id = resp.json()["task_id"]
        run_review_orchestrator(task_id, db_factory=smoke_db)

        metrics_resp = smoke_client.get("/api/metrics/dashboard", headers={"X-Demo-Owner": "smoke"})
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        assert metrics["total_tasks"] >= 1
        assert metrics["total_issues"] >= 1
        assert "risk_distribution" in metrics
