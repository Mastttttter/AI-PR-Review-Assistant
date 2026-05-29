from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apr_backend.db.enums import FeedbackStatus, TaskStatus
from apr_backend.db.models import IssueFeedback, ReviewIssue, ReviewTask
from apr_backend.db.session import get_db

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]
DbSession = Annotated[Session, Depends(get_db)]


class DashboardResponse(BaseModel):
    total_tasks: int
    tasks_last_30_days: int
    total_issues: int
    risk_distribution: dict[str, int]
    useful_rate: float
    false_positive_rate: float
    adoption_rate: float


def _count_tasks(db: Session, demo_owner: str) -> int:
    return db.scalar(
        select(func.count()).select_from(ReviewTask).where(
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
        )
    ) or 0


def _count_tasks_recent(db: Session, demo_owner: str, days: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return db.scalar(
        select(func.count()).select_from(ReviewTask).where(
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
            ReviewTask.created_at >= cutoff,
        )
    ) or 0


def _risk_distribution(db: Session, demo_owner: str) -> dict[str, int]:
    rows = db.execute(
        select(ReviewTask.risk_level, func.count()).where(
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
            ReviewTask.risk_level.isnot(None),
        ).group_by(ReviewTask.risk_level)
    ).all()
    dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for level, count in rows:
        if level and level.value in dist:
            dist[level.value] = count
    return dist


def _count_total_issues(db: Session, demo_owner: str) -> int:
    return db.scalar(
        select(func.count()).select_from(ReviewIssue).join(
            ReviewTask, ReviewIssue.task_id == ReviewTask.id
        ).where(
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
        )
    ) or 0


def _feedback_rate(db: Session, demo_owner: str, status: FeedbackStatus) -> float:
    total = db.scalar(
        select(func.count()).select_from(IssueFeedback).join(
            ReviewTask, IssueFeedback.task_id == ReviewTask.id
        ).where(
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
        )
    ) or 0

    if total == 0:
        return 0.0

    matching = db.scalar(
        select(func.count()).select_from(IssueFeedback).join(
            ReviewTask, IssueFeedback.task_id == ReviewTask.id
        ).where(
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
            IssueFeedback.feedback_status == status,
        )
    ) or 0

    return round(matching / total, 4)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_metrics(demo_owner: DemoOwnerHeader, db: DbSession) -> DashboardResponse:
    return DashboardResponse(
        total_tasks=_count_tasks(db, demo_owner),
        tasks_last_30_days=_count_tasks_recent(db, demo_owner),
        total_issues=_count_total_issues(db, demo_owner),
        risk_distribution=_risk_distribution(db, demo_owner),
        useful_rate=_feedback_rate(db, demo_owner, FeedbackStatus.useful),
        false_positive_rate=_feedback_rate(db, demo_owner, FeedbackStatus.false_positive),
        adoption_rate=_feedback_rate(db, demo_owner, FeedbackStatus.adopted),
    )
