from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apr_backend.db.enums import FeedbackStatus
from apr_backend.db.models import IssueFeedback, ReviewIssue, ReviewTask
from apr_backend.db.session import get_db

router = APIRouter(prefix="/api/review-issues", tags=["issue-feedback"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]
DbSession = Annotated[Session, Depends(get_db)]


class FeedbackUpdate(BaseModel):
    feedback_status: FeedbackStatus
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: str
    issue_id: str
    feedback_status: FeedbackStatus
    comment: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.patch("/{issue_id}/feedback", response_model=FeedbackResponse)
def update_issue_feedback(
    issue_id: str,
    payload: FeedbackUpdate,
    demo_owner: DemoOwnerHeader,
    db: DbSession,
) -> FeedbackResponse:
    issue = db.scalar(
        select(ReviewIssue).join(ReviewTask, ReviewIssue.task_id == ReviewTask.id).where(
            ReviewIssue.id == issue_id,
            ReviewTask.demo_owner == demo_owner,
        )
    )
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    issue.feedback_status = payload.feedback_status

    feedback = IssueFeedback(
        issue_id=issue.id,
        task_id=issue.task_id,
        demo_owner=demo_owner,
        feedback_status=payload.feedback_status,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return FeedbackResponse(
        id=feedback.id,
        issue_id=feedback.issue_id,
        feedback_status=feedback.feedback_status,
        comment=feedback.comment,
        created_at=feedback.created_at.isoformat(),
    )
