from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apr_backend.db.enums import RuleType, Severity
from apr_backend.db.models import ReviewRule
from apr_backend.db.session import get_db

router = APIRouter(prefix="/api/review-rules", tags=["review-rules"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]
DbSession = Annotated[Session, Depends(get_db)]


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    rule_type: RuleType
    severity: Severity
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    rule_type: RuleType
    severity: Severity
    enabled: bool


class RuleResponse(BaseModel):
    id: str
    name: str
    description: str
    rule_type: RuleType
    severity: Severity
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleCreate, demo_owner: DemoOwnerHeader, db: DbSession) -> RuleResponse:
    rule = ReviewRule(
        name=payload.name.strip(),
        description=payload.description.strip(),
        rule_type=payload.rule_type,
        severity=payload.severity,
        enabled=payload.enabled,
        demo_owner=demo_owner,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[RuleResponse])
def list_rules(demo_owner: DemoOwnerHeader, db: DbSession) -> list[RuleResponse]:
    rules = db.scalars(
        select(ReviewRule).where(
            ReviewRule.demo_owner == demo_owner,
            ReviewRule.deleted_at.is_(None),
        ).order_by(ReviewRule.created_at.desc())
    ).all()
    return list(rules)


@router.put("/{rule_id}", response_model=RuleResponse)
def update_rule(rule_id: str, payload: RuleUpdate, demo_owner: DemoOwnerHeader, db: DbSession) -> RuleResponse:
    rule = _get_owned_rule(db, rule_id, demo_owner)
    rule.name = payload.name.strip()
    rule.description = payload.description.strip()
    rule.rule_type = payload.rule_type
    rule.severity = payload.severity
    rule.enabled = payload.enabled
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}/enable", response_model=RuleResponse)
def enable_rule(rule_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> RuleResponse:
    rule = _get_owned_rule(db, rule_id, demo_owner)
    rule.enabled = True
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}/disable", response_model=RuleResponse)
def disable_rule(rule_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> RuleResponse:
    rule = _get_owned_rule(db, rule_id, demo_owner)
    rule.enabled = False
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str, demo_owner: DemoOwnerHeader, db: DbSession) -> Response:
    rule = _get_owned_rule(db, rule_id, demo_owner)
    rule.deleted_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_owned_rule(db: Session, rule_id: str, demo_owner: str) -> ReviewRule:
    rule = db.scalar(
        select(ReviewRule).where(
            ReviewRule.id == rule_id,
            ReviewRule.demo_owner == demo_owner,
            ReviewRule.deleted_at.is_(None),
        )
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule
