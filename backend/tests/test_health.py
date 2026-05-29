from fastapi.testclient import TestClient

from apr_backend.main import create_app


def test_health_reports_readiness_without_llm_call() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "AI PR Review Assistant",
        "environment": "local",
        "worker_queue": "review",
    }
