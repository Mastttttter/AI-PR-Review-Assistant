from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.review_tasks import get_db
from apr_backend.core.settings import get_settings
from apr_backend.main import create_app

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
def auth_db(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'auth.db'}"
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Sess = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    yield Sess
    get_settings.cache_clear()


def _make_client(auth_db, monkeypatch, api_key_setting: str | None = None):
    if api_key_setting is not None:
        monkeypatch.setenv("APR_API_KEY", api_key_setting)
    else:
        monkeypatch.delenv("APR_API_KEY", raising=False)
    get_settings.cache_clear()

    app = create_app()

    def override_get_db():
        with auth_db() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _create_task(client: TestClient, owner: str = "alice", *, api_key: str | None = None, extra_fields: dict | None = None) -> tuple[int, object]:
    payload = {"pr_title": "Test PR", "diff_content": MINIMAL_DIFF}
    if extra_fields:
        payload.update(extra_fields)
    headers = {"X-Demo-Owner": owner}
    if api_key:
        headers["X-API-Key"] = api_key
    resp = client.post("/api/review-tasks", json=payload, headers=headers)
    return resp.status_code, resp


class TestAPIKeyRequired:
    def test_missing_api_key_returns_401(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.post(
            "/api/review-tasks",
            json={"pr_title": "Test", "diff_content": MINIMAL_DIFF},
            headers={"X-Demo-Owner": "alice"},
        )
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.post(
            "/api/review-tasks",
            json={"pr_title": "Test", "diff_content": MINIMAL_DIFF},
            headers={"X-API-Key": "wrong-key", "X-Demo-Owner": "alice"},
        )
        assert resp.status_code == 401

    def test_correct_api_key_passes(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        status, resp = _create_task(client, owner="alice", api_key="demo-key")
        assert status == 201

    def test_correct_api_key_on_rules_endpoint(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.get("/api/review-rules", headers={"X-API-Key": "demo-key", "X-Demo-Owner": "alice"})
        assert resp.status_code == 200

    def test_correct_api_key_on_metrics_endpoint(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.get("/api/metrics/dashboard", headers={"X-API-Key": "demo-key", "X-Demo-Owner": "alice"})
        assert resp.status_code == 200

    def test_wrong_key_blocked_on_rules_endpoint(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.get("/api/review-rules", headers={"X-API-Key": "wrong-key", "X-Demo-Owner": "alice"})
        assert resp.status_code == 401

    def test_wrong_key_blocked_on_feedback_endpoint(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.patch(
            "/api/review-issues/nonexistent/feedback",
            json={"feedback_status": "useful"},
            headers={"X-API-Key": "wrong-key", "X-Demo-Owner": "alice"},
        )
        assert resp.status_code == 401


class TestAPIKeyNotConfigured:
    def test_no_api_key_configured_allows_all(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice")
        assert status == 201

    def test_no_api_key_rules_accessible(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        resp = client.get("/api/review-rules", headers={"X-Demo-Owner": "alice"})
        assert resp.status_code == 200

    def test_no_api_key_metrics_accessible(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        resp = client.get("/api/metrics/dashboard", headers={"X-Demo-Owner": "alice"})
        assert resp.status_code == 200


class TestExcludedPaths:
    def test_health_endpoint_no_key_required(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_docs_endpoint_no_key_required(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json_no_key_required(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting="demo-key")
        resp = client.get("/openapi.json")
        assert resp.status_code == 200


class TestOwnerNameValidation:
    def test_owner_name_matches_header_passes(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice", extra_fields={"owner_name": "alice"})
        assert status == 201
        body = resp.json()
        assert body["task_id"]
        assert body["status"] == "pending"

    def test_owner_name_mismatches_header_returns_400(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice", extra_fields={"owner_name": "bob"})
        assert status == 400
        assert "owner_name" in resp.json()["detail"]

    def test_owner_name_not_provided_passes(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice")
        assert status == 201

    def test_owner_name_empty_string_not_checked(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice", extra_fields={"owner_name": ""})
        assert status == 201


class TestOwnerIsolation:
    def test_other_owner_cannot_access_detail(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice")
        task_id = resp.json()["task_id"]

        detail = client.get(f"/api/review-tasks/{task_id}", headers={"X-Demo-Owner": "bob"})
        assert detail.status_code == 404

    def test_other_owner_cannot_delete(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice")
        task_id = resp.json()["task_id"]

        delete = client.delete(f"/api/review-tasks/{task_id}", headers={"X-Demo-Owner": "bob"})
        assert delete.status_code == 404

    def test_other_owner_cannot_rerun(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        status, resp = _create_task(client, owner="alice")
        task_id = resp.json()["task_id"]

        rerun = client.post(f"/api/review-tasks/{task_id}/rerun", headers={"X-Demo-Owner": "bob"})
        assert rerun.status_code == 404

    def test_other_owner_cannot_access_feedback(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)
        resp = client.patch(
            "/api/review-issues/nonexistent/feedback",
            json={"feedback_status": "useful"},
            headers={"X-Demo-Owner": "alice"},
        )
        assert resp.status_code == 404

    def test_rules_are_isolated_by_owner(self, auth_db, monkeypatch) -> None:
        client = _make_client(auth_db, monkeypatch, api_key_setting=None)

        client.post(
            "/api/review-rules",
            json={"name": "Alice rule", "description": "Test", "rule_type": "style", "severity": "low"},
            headers={"X-Demo-Owner": "alice"},
        )
        client.post(
            "/api/review-rules",
            json={"name": "Bob rule", "description": "Test", "rule_type": "style", "severity": "low"},
            headers={"X-Demo-Owner": "bob"},
        )

        alice_rules = client.get("/api/review-rules", headers={"X-Demo-Owner": "alice"})
        assert alice_rules.status_code == 200
        rules = alice_rules.json()
        assert len(rules) == 1
        assert rules[0]["name"] == "Alice rule"

        bob_rules = client.get("/api/review-rules", headers={"X-Demo-Owner": "bob"})
        bob_rules_list = bob_rules.json()
        assert len(bob_rules_list) == 1
        assert bob_rules_list[0]["name"] == "Bob rule"
