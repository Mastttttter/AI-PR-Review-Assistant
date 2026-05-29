from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apr_backend.core.settings import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ready"]
    service: str
    environment: str
    worker_queue: str


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ready",
        service=settings.app_name,
        environment=settings.environment,
        worker_queue=settings.review_queue_name,
    )
