from apr_backend.worker.entrypoint import main, readiness_payload


def test_worker_readiness_payload_uses_shared_settings() -> None:
    assert readiness_payload() == {
        "status": "ready",
        "queue": "review",
        "redis_url": "redis://localhost:6379/0",
    }


def test_worker_check_mode_starts_without_redis_or_llm() -> None:
    assert main(check_only=True) == 0
