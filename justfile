set dotenv-load := true

backend-dir := "backend"

backend-api:
    cd {{backend-dir}} && uv run uvicorn apr_backend.main:app --host ${APR_API_HOST:-0.0.0.0} --port ${APR_API_PORT:-8000}

backend-worker:
    cd {{backend-dir}} && uv run apr-worker

backend-worker-check:
    cd {{backend-dir}} && uv run apr-worker --check

backend-test:
    cd {{backend-dir}} && uv run --extra dev pytest
