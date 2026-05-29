import uvicorn
from fastapi import FastAPI

from apr_backend.api.health import router as health_router
from apr_backend.api.issue_feedback import router as issue_feedback_router
from apr_backend.api.review_rules import router as review_rules_router
from apr_backend.api.review_tasks import router as review_tasks_router
from apr_backend.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    app.include_router(review_rules_router)
    app.include_router(review_tasks_router)
    app.include_router(issue_feedback_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("apr_backend.main:app", host=settings.api_host, port=settings.api_port, reload=settings.environment == "local")
