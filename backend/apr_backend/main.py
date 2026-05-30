import uvicorn
from fastapi import FastAPI

from apr_backend.api.health import router as health_router
from apr_backend.api.issue_feedback import router as issue_feedback_router
from apr_backend.api.metrics import router as metrics_router
from apr_backend.api.review_rules import router as review_rules_router
from apr_backend.api.review_tasks import router as review_tasks_router
from apr_backend.core.auth import APIKeyMiddleware
from apr_backend.core.logging_config import configure_app_logging
from apr_backend.core.settings import get_settings

configure_app_logging()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(APIKeyMiddleware)
    app.include_router(health_router)
    app.include_router(review_rules_router)
    app.include_router(review_tasks_router)
    app.include_router(issue_feedback_router)
    app.include_router(metrics_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("apr_backend.main:app", host=settings.api_host, port=settings.api_port, reload=settings.environment == "local")
