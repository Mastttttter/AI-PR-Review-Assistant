from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from apr_backend.api.review_rules import get_db
from apr_backend.core.settings import get_settings
from apr_backend.db.enums import RuleType, Severity
from apr_backend.db.models import ReviewRule
from apr_backend.db.session import SessionLocal
from apr_backend.main import create_app


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'rules.db'}"
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

CREATE_PAYLOAD = {
    "name": "Ban console.log",
    "description": "No debug logging in production code.",
    "rule_type": "style",
    "severity": "low",
    "enabled": True,
}


class TestCreate:
    def test_creates_rule_and_returns_201(self, client) -> None:
        response = client.post("/api/review-rules", json=CREATE_PAYLOAD, headers=OWNER)
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Ban console.log"
        assert body["rule_type"] == "style"
        assert body["severity"] == "low"
        assert body["enabled"] is True

    def test_requires_name_and_description(self, client) -> None:
        assert client.post("/api/review-rules", json={**CREATE_PAYLOAD, "name": ""}, headers=OWNER).status_code == 422
        assert client.post("/api/review-rules", json={**CREATE_PAYLOAD, "description": ""}, headers=OWNER).status_code == 422

    def test_invalid_rule_type_rejected(self, client) -> None:
        response = client.post("/api/review-rules", json={**CREATE_PAYLOAD, "rule_type": "bogus"}, headers=OWNER)
        assert response.status_code == 422

    def test_invalid_severity_rejected(self, client) -> None:
        response = client.post("/api/review-rules", json={**CREATE_PAYLOAD, "severity": "fatal"}, headers=OWNER)
        assert response.status_code == 422

    def test_creates_with_enabled_false(self, client) -> None:
        response = client.post("/api/review-rules", json={**CREATE_PAYLOAD, "enabled": False}, headers=OWNER)
        assert response.status_code == 201
        assert response.json()["enabled"] is False


class TestList:
    def test_lists_owned_rules_excluding_deleted(self, client, session_factory) -> None:
        with session_factory() as session:
            session.add_all([
                ReviewRule(name="R1", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a"),
                ReviewRule(name="R2", description="d", rule_type=RuleType.security, severity=Severity.high, enabled=False, demo_owner="owner-a"),
                ReviewRule(name="Other", description="d", rule_type=RuleType.test, severity=Severity.medium, enabled=True, demo_owner="owner-b"),
                ReviewRule(name="Deleted", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a", deleted_at=datetime.now(UTC)),
            ])
            session.commit()

        response = client.get("/api/review-rules", headers=OWNER)
        assert response.status_code == 200
        names = [r["name"] for r in response.json()]
        assert names == ["R2", "R1"]


class TestUpdate:
    def test_full_update_replaces_fields(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="Old", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a")
            session.add(rule)
            session.commit()
            rid = rule.id

        updated = {**CREATE_PAYLOAD, "name": "New name", "severity": "high", "rule_type": "security", "enabled": False}
        response = client.put(f"/api/review-rules/{rid}", json=updated, headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "New name"
        assert body["severity"] == "high"
        assert body["rule_type"] == "security"
        assert body["enabled"] is False

    def test_update_deleted_rule_returns_404(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="D", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a", deleted_at=datetime.now(UTC))
            session.add(rule)
            session.commit()
            rid = rule.id

        response = client.put(f"/api/review-rules/{rid}", json=CREATE_PAYLOAD, headers=OWNER)
        assert response.status_code == 404

    def test_update_other_owner_returns_404(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="O", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-b")
            session.add(rule)
            session.commit()
            rid = rule.id

        response = client.put(f"/api/review-rules/{rid}", json=CREATE_PAYLOAD, headers=OWNER)
        assert response.status_code == 404


class TestEnableDisable:
    def test_enable_sets_true(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="R", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=False, demo_owner="owner-a")
            session.add(rule)
            session.commit()
            rid = rule.id

        response = client.patch(f"/api/review-rules/{rid}/enable", headers=OWNER)
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_disable_sets_false(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="R", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a")
            session.add(rule)
            session.commit()
            rid = rule.id

        response = client.patch(f"/api/review-rules/{rid}/disable", headers=OWNER)
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_enable_idempotent(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="R", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a")
            session.add(rule)
            session.commit()
            rid = rule.id

        r1 = client.patch(f"/api/review-rules/{rid}/enable", headers=OWNER)
        r2 = client.patch(f"/api/review-rules/{rid}/enable", headers=OWNER)
        assert r1.status_code == 200
        assert r2.status_code == 200


class TestDelete:
    def test_delete_sets_deleted_at(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="R", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a")
            session.add(rule)
            session.commit()
            rid = rule.id

        response = client.delete(f"/api/review-rules/{rid}", headers=OWNER)
        assert response.status_code == 204

        with session_factory() as session:
            deleted = session.get(ReviewRule, rid)
            assert deleted.deleted_at is not None

    def test_deleted_rule_excluded_from_list(self, client, session_factory) -> None:
        with session_factory() as session:
            rule = ReviewRule(name="R", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a")
            session.add(rule)
            session.commit()
            rid = rule.id

        client.delete(f"/api/review-rules/{rid}", headers=OWNER)
        response = client.get("/api/review-rules", headers=OWNER)
        assert response.json() == []


class TestWorkerRuleLoading:
    def test_enabled_rules_are_queryable_by_worker(self, client, session_factory) -> None:
        with session_factory() as session:
            session.add_all([
                ReviewRule(name="Enabled", description="e", rule_type=RuleType.style, severity=Severity.low, enabled=True, demo_owner="owner-a"),
                ReviewRule(name="Disabled", description="d", rule_type=RuleType.security, severity=Severity.high, enabled=False, demo_owner="owner-a"),
            ])
            session.commit()

        with session_factory() as session:
            enabled = list(session.scalars(
                select(ReviewRule).where(
                    ReviewRule.demo_owner == "owner-a",
                    ReviewRule.enabled.is_(True),
                    ReviewRule.deleted_at.is_(None),
                )
            ).all())
            assert len(enabled) == 1
            assert enabled[0].name == "Enabled"

    def test_disabled_rule_not_available_to_worker(self, client, session_factory) -> None:
        with session_factory() as session:
            session.add(ReviewRule(name="D", description="d", rule_type=RuleType.style, severity=Severity.low, enabled=False, demo_owner="owner-a"))
            session.commit()

        with session_factory() as session:
            enabled = list(session.scalars(
                select(ReviewRule).where(ReviewRule.demo_owner == "owner-a", ReviewRule.enabled.is_(True), ReviewRule.deleted_at.is_(None))
            ).all())
            assert len(enabled) == 0
