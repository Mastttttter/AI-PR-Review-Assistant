from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from apr_backend.api.review_rules import get_db
from apr_backend.core.settings import get_settings
from apr_backend.main import create_app


OWNER = {"X-Demo-Owner": "owner-a"}

SAMPLE_CONFIG = {
    "openai": {"base_uri": "https://custom.openai.com/v1", "api_key": "sk-test-key-1234", "model": "gpt-4"},
    "anthropic": {"base_uri": "https://custom.anthropic.com", "api_key": "sk-ant-test-5678", "model": "claude-opus-4-7"},
}


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_url = f"sqlite:///{tmp_path / 'settings.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    monkeypatch.setenv("APR_DATABASE_URL", database_url)
    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        with sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def clean_config(monkeypatch):
    monkeypatch.setenv("APR_OPENAI_BASE_URI", "https://api.openai.com/v1")
    monkeypatch.setenv("APR_OPENAI_API_KEY", "sk-env-key-openai")
    monkeypatch.setenv("APR_OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("APR_ANTHROPIC_BASE_URI", "https://api.anthropic.com")
    monkeypatch.setenv("APR_ANTHROPIC_API_KEY", "sk-env-key-anthropic")
    monkeypatch.setenv("APR_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestGetSettings:
    def test_returns_env_var_defaults_when_no_config_file(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.api.settings.load_llm_config",
            lambda: {
                "active_provider": "openai",
                "mock_enabled": False,
                "timeout": 60,
                "openai": {"base_uri": "https://test.openai.com", "api_key": "sk-abc123", "model": "test-model"},
                "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": "sk-ant-key", "model": "claude-sonnet-4-6"},
            },
        )
        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["openai"]["base_uri"] == "https://test.openai.com"
        assert body["openai"]["model"] == "test-model"
        assert body["anthropic"]["base_uri"] == "https://api.anthropic.com"
        assert body["active_provider"] == "openai"
        assert body["mock_enabled"] is False

    def test_masks_api_keys(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.api.settings.load_llm_config",
            lambda: {
                "active_provider": "openai",
                "mock_enabled": False,
                "timeout": 60,
                "openai": {"base_uri": "https://api.openai.com/v1", "api_key": "sk-abcdefgh12345678", "model": "gpt-4o-mini"},
                "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": "sk-ant-short", "model": "claude-sonnet-4-6"},
            },
        )
        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["openai"]["api_key"] == "***-5678"
        assert body["anthropic"]["api_key"] == "***-hort"

    def test_masks_none_api_key(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.api.settings.load_llm_config",
            lambda: {
                "active_provider": "openai",
                "mock_enabled": False,
                "timeout": 60,
                "openai": {"base_uri": "https://api.openai.com/v1", "api_key": None, "model": "gpt-4o-mini"},
                "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": None, "model": "claude-sonnet-4-6"},
            },
        )
        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["openai"]["api_key"] is None

    def test_includes_system_prompt(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            "apr_backend.api.settings.load_llm_config",
            lambda: {
                "active_provider": "openai",
                "mock_enabled": False,
                "timeout": 60,
                "system_prompt": "Custom system instructions.",
                "openai": {"base_uri": "https://api.openai.com/v1", "api_key": "sk-key", "model": "gpt-4o-mini"},
                "anthropic": {"base_uri": "https://api.anthropic.com", "api_key": None, "model": "claude-sonnet-4-6"},
            },
        )
        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["system_prompt"] == "Custom system instructions."


class TestPutSettings:
    def test_creates_config_file_with_correct_content(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        response = client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)
        assert response.status_code == 200
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved == SAMPLE_CONFIG

    def test_updates_existing_config_file(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)

        client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)

        updated_cfg = {
            "openai": {"base_uri": "https://new.openai.com", "api_key": "sk-new-key", "model": "gpt-4o"},
            "anthropic": {"base_uri": "https://new.anthropic.com", "api_key": "sk-new-ant", "model": "claude-sonnet-4-6"},
        }
        response = client.put("/api/settings", json=updated_cfg, headers=OWNER)
        assert response.status_code == 200
        saved = json.loads(config_path.read_text())
        assert saved == updated_cfg

    def test_get_returns_config_file_values_over_env(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)

        monkeypatch.setenv("APR_OPENAI_BASE_URI", "https://env.openai.com")
        monkeypatch.setenv("APR_OPENAI_MODEL", "env-model")
        monkeypatch.setenv("APR_OPENAI_API_KEY", "sk-env-key")
        get_settings.cache_clear()

        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["openai"]["base_uri"] == "https://custom.openai.com/v1"
        assert body["openai"]["model"] == "gpt-4"
        assert body["anthropic"]["base_uri"] == "https://custom.anthropic.com"

    def test_put_active_provider_and_mock_get_returns_them(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        payload = {
            "active_provider": "anthropic",
            "mock_enabled": True,
            "openai": {"base_uri": "https://openai.example.com", "api_key": "sk-openai", "model": "gpt-4"},
            "anthropic": {"base_uri": "https://anthropic.example.com", "api_key": "sk-ant", "model": "claude-opus-4-7"},
        }
        client.put("/api/settings", json=payload, headers=OWNER)
        get_settings.cache_clear()

        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["active_provider"] == "anthropic"
        assert body["mock_enabled"] is True

    def test_put_persists_system_prompt(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        payload = {
            "system_prompt": "Be extra careful with security.",
            "openai": {"base_uri": "https://openai.example.com", "api_key": "sk-openai", "model": "gpt-4"},
            "anthropic": {"base_uri": "https://anthropic.example.com", "api_key": "sk-ant", "model": "claude-opus-4-7"},
        }
        client.put("/api/settings", json=payload, headers=OWNER)
        get_settings.cache_clear()

        response = client.get("/api/settings", headers=OWNER)
        assert response.status_code == 200
        body = response.json()
        assert body["system_prompt"] == "Be extra careful with security."


class TestPostTestSettings:
    def test_returns_success_for_valid_response(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "Hi"}}]}

            payload = {"provider": "openai", "base_uri": "https://api.openai.com/v1", "api_key": "sk-test", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            assert response.json()["success"] is True
            assert "Connected successfully" in response.json()["message"]

    def test_returns_success_for_anthropic_valid_response(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"content": [{"type": "text", "text": "Hi"}]}

            payload = {"provider": "anthropic", "base_uri": "https://api.anthropic.com", "api_key": "sk-test", "model": "claude-sonnet-4-6"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_returns_failure_for_invalid_uri(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post", side_effect=__import__("httpx").RequestError("Connection refused")):
            payload = {"provider": "openai", "base_uri": "https://nonexistent.example.com", "api_key": "sk-test", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            assert response.json()["success"] is False
            assert "Connection failed" in response.json()["message"]

    def test_returns_failure_for_invalid_api_key(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 401
            mock_post.return_value.text = "Unauthorized"

            payload = {"provider": "openai", "base_uri": "https://api.openai.com/v1", "api_key": "sk-bad", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is False
            assert "Invalid API key" in body["message"]

    def test_returns_failure_for_403(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 403
            mock_post.return_value.text = "Forbidden"

            payload = {"provider": "anthropic", "base_uri": "https://api.anthropic.com", "api_key": "sk-bad", "model": "claude-sonnet-4-6"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is False
            assert "Invalid API key" in body["message"]

    def test_returns_failure_for_timeout(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post", side_effect=__import__("httpx").TimeoutException("timeout")):
            payload = {"provider": "openai", "base_uri": "https://api.openai.com/v1", "api_key": "sk-test", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is False
            assert "timed out" in body["message"]

    def test_returns_failure_for_server_error(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 500
            mock_post.return_value.text = "Internal Server Error"

            payload = {"provider": "openai", "base_uri": "https://api.openai.com/v1", "api_key": "sk-test", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is False
            assert "Connection failed" in body["message"]

    def test_requires_demo_owner_header(self, client, clean_config) -> None:
        response = client.get("/api/settings")
        assert response.status_code == 422


class TestPutPreservesKey:
    def test_preserves_existing_key_when_masked_value_sent(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)

        masked_payload = {
            "openai": {"base_uri": "https://custom.openai.com/v1", "api_key": "***-1234", "model": "gpt-4"},
            "anthropic": {"base_uri": "https://custom.anthropic.com", "api_key": "***-5678", "model": "claude-opus-4-7"},
        }
        response = client.put("/api/settings", json=masked_payload, headers=OWNER)
        assert response.status_code == 200
        saved = json.loads(config_path.read_text())
        assert saved["openai"]["api_key"] == "sk-test-key-1234"
        assert saved["anthropic"]["api_key"] == "sk-ant-test-5678"

    def test_preserves_existing_key_when_empty_string_sent(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)

        empty_key_payload = {
            "openai": {"base_uri": "https://custom.openai.com/v1", "api_key": "", "model": "gpt-4"},
            "anthropic": {"base_uri": "https://custom.anthropic.com", "api_key": "", "model": "claude-opus-4-7"},
        }
        response = client.put("/api/settings", json=empty_key_payload, headers=OWNER)
        assert response.status_code == 200
        saved = json.loads(config_path.read_text())
        assert saved["openai"]["api_key"] == "sk-test-key-1234"
        assert saved["anthropic"]["api_key"] == "sk-ant-test-5678"

    def test_writes_new_key_when_real_value_sent(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)

        client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)

        new_key_payload = {
            "openai": {"base_uri": "https://custom.openai.com/v1", "api_key": "sk-brand-new-key", "model": "gpt-4"},
            "anthropic": {"base_uri": "https://custom.anthropic.com", "api_key": "sk-ant-new-key", "model": "claude-opus-4-7"},
        }
        response = client.put("/api/settings", json=new_key_payload, headers=OWNER)
        assert response.status_code == 200
        saved = json.loads(config_path.read_text())
        assert saved["openai"]["api_key"] == "sk-brand-new-key"
        assert saved["anthropic"]["api_key"] == "sk-ant-new-key"


class TestPostUsesStoredKey:
    def test_uses_stored_key_when_api_key_not_provided(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_dir)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        client.put("/api/settings", json=SAMPLE_CONFIG, headers=OWNER)
        get_settings.cache_clear()

        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "Hi"}}]}

            payload = {"provider": "openai", "base_uri": "https://custom.openai.com/v1", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            assert response.json()["success"] is True
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key-1234"

    def test_uses_provided_key_when_real_value_sent(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "Hi"}}]}

            payload = {"provider": "openai", "base_uri": "https://api.openai.com/v1", "api_key": "sk-direct-key", "model": "gpt-4"}
            response = client.post("/api/settings/test", json=payload, headers=OWNER)
            assert response.status_code == 200
            assert response.json()["success"] is True
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-direct-key"

    def test_returns_failure_when_no_key_configured(self, client, clean_config, tmp_path, monkeypatch) -> None:
        config_path = tmp_path / "nonexistent" / "config.json"
        monkeypatch.setattr("apr_backend.api.settings.CONFIG_PATH", config_path)
        monkeypatch.setattr("apr_backend.api.settings._CONFIG_DIR", config_path.parent)
        monkeypatch.setattr("apr_backend.core.config_loader._CONFIG_PATH", config_path)
        monkeypatch.setenv("APR_OPENAI_API_KEY", "")
        monkeypatch.setenv("APR_LLM_API_KEY", "")
        get_settings.cache_clear()

        payload = {"provider": "openai", "base_uri": "https://api.openai.com/v1", "model": "gpt-4"}
        response = client.post("/api/settings/test", json=payload, headers=OWNER)
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "No API key" in response.json()["message"]


class TestDispatcherFetch:
    DISPATCHER_RESPONSE = {
        "api_key": "tmp-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "base_uri": "http://dispatcher:8318",
        "model": "gpt-4o-mini",
        "expires_in": 600,
    }

    def test_success_returns_credentials(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.is_success = True
            mock_post.return_value.json.return_value = self.DISPATCHER_RESPONSE

            response = client.post(
                "/api/settings/dispatcher-fetch",
                json={"url": "http://localhost:8318"},
                headers=OWNER,
            )
            assert response.status_code == 200
            body = response.json()
            assert body["api_key"] == self.DISPATCHER_RESPONSE["api_key"]
            assert body["model"] == self.DISPATCHER_RESPONSE["model"]
            assert body["expires_in"] == self.DISPATCHER_RESPONSE["expires_in"]
            assert body["base_uri"] == "http://localhost:8318"

    def test_base_uri_overrides_dispatcher_response(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.is_success = True
            mock_post.return_value.json.return_value = self.DISPATCHER_RESPONSE

            response = client.post(
                "/api/settings/dispatcher-fetch",
                json={"url": "http://10.0.0.5:9999"},
                headers=OWNER,
            )
            assert response.status_code == 200
            body = response.json()
            assert body["base_uri"] == "http://10.0.0.5:9999"

    def test_connection_error_returns_502(self, client, clean_config) -> None:
        import httpx as httpx_mod
        with patch("apr_backend.api.settings.httpx.post", side_effect=httpx_mod.ConnectError("connection refused")):
            response = client.post(
                "/api/settings/dispatcher-fetch",
                json={"url": "http://localhost:8318"},
                headers=OWNER,
            )
            assert response.status_code == 502
            assert "connection refused" in response.json()["detail"].lower()

    def test_timeout_returns_502(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post", side_effect=__import__("httpx").TimeoutException("timeout")):
            response = client.post(
                "/api/settings/dispatcher-fetch",
                json={"url": "http://localhost:8318"},
                headers=OWNER,
            )
            assert response.status_code == 502
            assert "timed out" in response.json()["detail"].lower()

    def test_dispatcher_non_200_returns_502(self, client, clean_config) -> None:
        with patch("apr_backend.api.settings.httpx.post") as mock_post:
            mock_post.return_value.status_code = 500
            mock_post.return_value.is_success = False
            mock_post.return_value.text = "Internal Server Error"

            response = client.post(
                "/api/settings/dispatcher-fetch",
                json={"url": "http://localhost:8318"},
                headers=OWNER,
            )
            assert response.status_code == 502
            assert "Internal Server Error" in response.json()["detail"]

    def test_requires_demo_owner_header(self, client, clean_config) -> None:
        response = client.post(
            "/api/settings/dispatcher-fetch",
            json={"url": "http://localhost:8318"},
        )
        assert response.status_code == 422
