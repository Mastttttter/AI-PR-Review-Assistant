import json
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from apr_backend.db.enums import Confidence, FeedbackStatus, IssueType, RiskLevel, Severity, TaskStatus
from apr_backend.db.models import ReviewIssue, ReviewTask
from apr_backend.db.session import get_db
from apr_backend.worker.queue import enqueue_review_job

router = APIRouter(prefix="/api/review-tasks", tags=["review-tasks"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]
DbSession = Annotated[Session, Depends(get_db)]


class ReviewTaskCreate(BaseModel):
    pr_title: str = Field(min_length=1, max_length=255)
    pr_description: str | None = None
    pr_url: str | None = Field(default=None, max_length=2048)
    project_name: str | None = Field(default=None, max_length=255)
    target_branch: str | None = Field(default=None, max_length=255)
    developer_name: str | None = Field(default=None, max_length=255)
    owner_name: str | None = Field(default=None, max_length=255)
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
    pr_url: str | None
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
    pr_url: str | None
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
    if payload.owner_name and payload.owner_name != demo_owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="owner_name does not match X-Demo-Owner header")
    task = ReviewTask(
        pr_title=payload.pr_title.strip(),
        pr_description=payload.pr_description,
        pr_url=payload.pr_url,
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


class ReportTaskNested(BaseModel):
    id: str
    pr_title: str
    pr_description: str | None
    pr_url: str | None
    project_name: str | None
    target_branch: str | None
    developer_name: str | None
    status: TaskStatus
    risk_level: RiskLevel | None
    issue_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportSummaryResponse(BaseModel):
    purpose: str = ""
    changed_modules: list[str] = []
    key_files: list[str] = []
    business_impact: str = ""
    test_or_security_notes: str = ""


class ReportRiskResponse(BaseModel):
    level: RiskLevel | None = None
    reasons: list[str] = []


class IssueLocationResponse(BaseModel):
    file_path: str | None = None
    line_hint: str | None = None
    code_snippet: str | None = None


class ReportIssueResponse(BaseModel):
    id: str
    task_id: str
    report_id: str
    title: str
    type: IssueType
    severity: Severity
    description: str
    location: IssueLocationResponse
    suggestion: str
    confidence: Confidence
    matched_rule_ids: list[str]
    feedback_status: FeedbackStatus
    created_at: datetime


class IssueStatsResponse(BaseModel):
    total: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    rule_hits: int = 0


class ReportResponse(BaseModel):
    id: str
    task: ReportTaskNested
    summary: ReportSummaryResponse | None = None
    risk: ReportRiskResponse
    issue_stats: IssueStatsResponse
    issues: list[ReportIssueResponse]
    created_at: datetime


_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    return []


def _parse_summary(raw: str | None) -> ReportSummaryResponse | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ReportSummaryResponse(purpose=raw)
    if not isinstance(data, dict):
        return ReportSummaryResponse(purpose=raw)
    return ReportSummaryResponse(
        purpose=data.get("purpose", ""),
        changed_modules=_normalize_list(data.get("changed_modules", [])),
        key_files=_normalize_list(data.get("key_files", [])),
        business_impact=data.get("business_impact", ""),
        test_or_security_notes=data.get("test_or_security_notes", ""),
    )


def _build_issue_response(issue: ReviewIssue) -> ReportIssueResponse:
    sev = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)
    itype = issue.issue_type.value if hasattr(issue.issue_type, "value") else str(issue.issue_type)
    conf = issue.confidence.value if hasattr(issue.confidence, "value") else str(issue.confidence)
    fb = issue.feedback_status.value if hasattr(issue.feedback_status, "value") else str(issue.feedback_status)
    return ReportIssueResponse(
        id=issue.id,
        task_id=issue.task_id,
        report_id=issue.report_id,
        title=issue.title,
        type=IssueType(itype),
        severity=Severity(sev),
        description=issue.description,
        location=IssueLocationResponse(
            file_path=issue.file_path,
            line_hint=issue.line_hint,
            code_snippet=issue.code_snippet,
        ),
        suggestion=issue.suggestion,
        confidence=Confidence(conf),
        matched_rule_ids=issue.matched_rule_ids or [],
        feedback_status=FeedbackStatus(fb),
        created_at=issue.created_at,
    )


@router.get("/{task_id}/report", response_model=ReportResponse)
def get_review_report(task_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> ReportResponse:
    task = get_owned_active_task(db, task_id, demo_owner)

    report = task.report

    summary = _parse_summary(report.summary if report else None)

    risk_level = report.risk_level if report else None
    risk_reasons = report.risk_reasons if report and report.risk_reasons else []
    risk = ReportRiskResponse(level=risk_level, reasons=risk_reasons)

    issues = list(db.scalars(
        select(ReviewIssue).where(ReviewIssue.task_id == task_id).order_by(ReviewIssue.created_at)
    ).all())

    sorted_issues = sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i.severity.value if hasattr(i.severity, "value") else str(i.severity), 99))
    issue_responses = [_build_issue_response(i) for i in sorted_issues]

    rule_hits = sum(1 for i in issues if i.matched_rule_ids)
    raw_stats = report.issue_stats if report and report.issue_stats else {}
    issue_stats = IssueStatsResponse(
        total=raw_stats.get("total", len(issues)),
        high=raw_stats.get("high", sum(1 for i in issues if (i.severity.value if hasattr(i.severity, "value") else str(i.severity)) == "high")),
        medium=raw_stats.get("medium", sum(1 for i in issues if (i.severity.value if hasattr(i.severity, "value") else str(i.severity)) == "medium")),
        low=raw_stats.get("low", sum(1 for i in issues if (i.severity.value if hasattr(i.severity, "value") else str(i.severity)) == "low")),
        rule_hits=rule_hits,
    )

    task_nested = ReportTaskNested(
        id=task.id,
        pr_title=task.pr_title,
        pr_description=task.pr_description,
        pr_url=task.pr_url,
        project_name=task.project_name,
        target_branch=task.target_branch,
        developer_name=task.developer_name,
        status=task.status,
        risk_level=task.risk_level,
        issue_count=task.issue_count,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )

    report_created_at = report.created_at if report else task.created_at

    return ReportResponse(
        id=report.id if report else task.id,
        task=task_nested,
        summary=summary,
        risk=risk,
        issue_stats=issue_stats,
        issues=issue_responses,
        created_at=report_created_at,
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
