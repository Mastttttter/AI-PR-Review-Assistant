from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from apr_backend.db.enums import Confidence, FeedbackStatus, IssueType, RiskLevel, TaskStatus
from apr_backend.db.models import ReviewIssue, ReviewTask
from apr_backend.db.session import get_db
from apr_backend.worker.queue import enqueue_review_job

router = APIRouter(prefix="/api/review-tasks", tags=["review-tasks"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]
DbSession = Annotated[Session, Depends(get_db)]


class ReviewTaskCreate(BaseModel):
    pr_title: str = Field(min_length=1, max_length=255)
    pr_description: str | None = None
    project_name: str | None = Field(default=None, max_length=255)
    target_branch: str | None = Field(default=None, max_length=255)
    developer_name: str | None = Field(default=None, max_length=255)
    diff_content: str = Field(min_length=1, max_length=50_000)

    @field_validator("pr_title", "diff_content")
    @classmethod
    def reject_blank_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field cannot be blank")
        return value


class ReviewTaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus


class ReviewTaskDetailResponse(BaseModel):
    id: str
    pr_title: str
    pr_description: str | None
    project_name: str | None
    target_branch: str | None
    developer_name: str | None
    demo_owner: str
    diff_content: str
    status: TaskStatus
    risk_level: RiskLevel | None
    issue_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewTaskListItem(BaseModel):
    id: str
    pr_title: str
    project_name: str | None
    developer_name: str | None
    status: TaskStatus
    risk_level: RiskLevel | None
    issue_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=ReviewTaskCreateResponse, status_code=status.HTTP_201_CREATED)
def create_review_task(payload: ReviewTaskCreate, demo_owner: DemoOwnerHeader, db: DbSession) -> ReviewTaskCreateResponse:
    task = ReviewTask(
        pr_title=payload.pr_title.strip(),
        pr_description=payload.pr_description,
        project_name=payload.project_name,
        target_branch=payload.target_branch,
        developer_name=payload.developer_name,
        demo_owner=demo_owner,
        diff_content=payload.diff_content,
        status=TaskStatus.pending,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    enqueue_review_job(task.id)
    return ReviewTaskCreateResponse(task_id=task.id, status=task.status)


@router.get("", response_model=list[ReviewTaskListItem])
def list_review_tasks(
    demo_owner: DemoOwnerHeader,
    db: DbSession,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    project_name: str | None = None,
    risk_level: RiskLevel | None = None,
    created_after: date | None = None,
    created_before: date | None = None,
) -> list[ReviewTask]:
    statement = select(ReviewTask).where(ReviewTask.demo_owner == demo_owner, ReviewTask.deleted_at.is_(None))
    if status_filter is not None:
        statement = statement.where(ReviewTask.status == status_filter)
    if project_name:
        statement = statement.where(ReviewTask.project_name == project_name)
    if risk_level is not None:
        statement = statement.where(ReviewTask.risk_level == risk_level)
    if created_after is not None:
        statement = statement.where(ReviewTask.created_at >= created_after)
    if created_before is not None:
        statement = statement.where(ReviewTask.created_at < created_before)
    statement = statement.order_by(ReviewTask.created_at.desc())
    return list(db.scalars(statement).all())


@router.get("/{task_id}", response_model=ReviewTaskDetailResponse)
def get_review_task(task_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> ReviewTask:
    return get_owned_active_task(db, task_id, demo_owner)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review_task(task_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> Response:
    task = get_owned_active_task(db, task_id, demo_owner)
    task.status = TaskStatus.deleted
    task.deleted_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/rerun", response_model=ReviewTaskCreateResponse)
def rerun_review_task(task_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> ReviewTaskCreateResponse:
    task = get_owned_active_task(db, task_id, demo_owner)
    task.status = TaskStatus.pending
    task.risk_level = None
    task.issue_count = 0
    task.error_message = None
    db.commit()
    db.refresh(task)
    enqueue_review_job(task.id)
    return ReviewTaskCreateResponse(task_id=task.id, status=task.status)


class ReportIssueResponse(BaseModel):
    id: str
    title: str
    issue_type: IssueType
    severity: str
    description: str
    file_path: str | None
    line_hint: str | None
    code_snippet: str | None
    suggestion: str
    confidence: Confidence
    matched_rule_ids: list[str]
    feedback_status: FeedbackStatus

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    id: str
    pr_title: str
    pr_description: str | None
    project_name: str | None
    target_branch: str | None
    developer_name: str | None
    status: TaskStatus
    risk_level: RiskLevel | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    summary: str | None
    risk_reasons: list[str]
    issue_stats: dict
    issues: list[ReportIssueResponse]

    model_config = {"from_attributes": True}


_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


@router.get("/{task_id}/report", response_model=ReportResponse)
def get_review_report(task_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> ReportResponse:
    task = get_owned_active_task(db, task_id, demo_owner)

    report = task.report
    summary = report.summary if report and report.summary else None
    risk_reasons = report.risk_reasons if report and report.risk_reasons else []
    issue_stats = report.issue_stats if report and report.issue_stats else {}

    issues = db.scalars(
        select(ReviewIssue).where(
            ReviewIssue.task_id == task_id,
        ).order_by(ReviewIssue.created_at)
    ).all()

    sorted_issues = sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i.severity.value if hasattr(i.severity, 'value') else str(i.severity), 99))

    return ReportResponse(
        id=task.id,
        pr_title=task.pr_title,
        pr_description=task.pr_description,
        project_name=task.project_name,
        target_branch=task.target_branch,
        developer_name=task.developer_name,
        status=task.status,
        risk_level=task.risk_level,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        summary=summary,
        risk_reasons=risk_reasons,
        issue_stats=issue_stats,
        issues=sorted_issues,
    )


def get_owned_active_task(db: Session, task_id: str, demo_owner: str) -> ReviewTask:
    task = db.scalar(
        select(ReviewTask).where(
            ReviewTask.id == task_id,
            ReviewTask.demo_owner == demo_owner,
            ReviewTask.deleted_at.is_(None),
        )
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")
    return task
