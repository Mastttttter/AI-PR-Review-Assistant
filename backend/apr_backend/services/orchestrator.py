from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from apr_backend.db.enums import Confidence, FeedbackStatus, IssueType, RiskLevel, Severity, TaskStatus
from apr_backend.db.models import ReviewReport, ReviewIssue, ReviewRule, ReviewTask
from apr_backend.db.session import SessionLocal
from apr_backend.services.diff_parser import ParsedDiff, parse_diff
from apr_backend.services.llm_adapter import LLMError, LLMProvider, LLMTimeoutError, create_llm_provider
from apr_backend.services.rule_engine import RuleMatch, run_rule_engine

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an AI PR Review assistant. You analyze code diffs and produce structured reviews.
You may only analyze the provided PR title, description, diff, and team rules.
Do not assume repository context beyond what is provided.
Do not output auto-modified code. Do not suggest auto-merging PRs.
Always output valid JSON matching the requested schema."""

REVIEW_POLICY_PROMPT = """\
Issue types: logic, exception, security, performance, maintainability, test_missing, rule_violation.
Severity levels: low, medium, high.
Risk levels: low, medium, high.

Rules for risk assessment:
- High-risk issues must have clear, specific reasons.
- Uncertain issues should have confidence lowered.
- Issues must include a suggestion for improvement.
- Issues should be sorted by severity (high first)."""


def _build_prompt(task: ReviewTask, parsed: ParsedDiff, rule_matches: list[RuleMatch], rules: list[ReviewRule]) -> str:
    parts: list[str] = [SYSTEM_PROMPT, "", REVIEW_POLICY_PROMPT]

    if rules:
        rules_json = [{"id": r.id, "name": r.name, "type": r.rule_type.value, "severity": r.severity.value, "description": r.description} for r in rules]
        parts.extend(["", "## Team Rules", json.dumps(rules_json, indent=2)])

    if rule_matches:
        matches_json = [{"rule_id": m.rule_id, "rule_name": m.rule_name, "description": m.description, "file_path": m.file_path, "line_hint": m.line_hint} for m in rule_matches]
        parts.extend(["", "## Pre-matched Rule Results (for context)", "These rules were matched deterministically. Include their rule_id values in matched_rule_ids for any related issues.", json.dumps(matches_json, indent=2)])

    parts.extend([
        "",
        "## PR Context",
        f"PR Title: {task.pr_title}",
    ])
    if task.pr_description:
        parts.append(f"PR Description: {task.pr_description}")
    if task.project_name:
        parts.append(f"Project: {task.project_name}")
    if task.target_branch:
        parts.append(f"Target Branch: {task.target_branch}")

    parts.extend([
        "",
        f"## Diff Metrics",
        f"Files changed: {parsed.metrics.file_count}",
        f"Added lines: {parsed.metrics.added_lines}",
        f"Deleted lines: {parsed.metrics.deleted_lines}",
        f"Contains test files: {parsed.metrics.contains_test_file}",
        f"Sensitive keywords detected: {', '.join(parsed.metrics.sensitive_keywords) if parsed.metrics.sensitive_keywords else 'none'}",
        "",
        "## Diff Content",
        task.diff_content,
        "",
        "Output a JSON object with keys: summary, risk, issues.",
        "summary: {purpose, changed_modules, key_files, business_impact, test_or_security_notes}",
        "risk: {level, reasons}",
        "issues: [{title, type, severity, description, location: {file_path, line_hint, code_snippet}, suggestion, confidence, matched_rule_ids}]",
        "matched_rule_ids must be a list of rule_id values from the Pre-matched Rule Results section (empty list if none apply).",
    ])

    return "\n".join(parts)


def _validate_and_normalize_ai_output(raw: dict, rule_match_ids: set[str]) -> dict:
    risk = raw.get("risk", {})
    level = risk.get("level", "low")
    if level not in {"low", "medium", "high"}:
        risk["level"] = "low"
    if not isinstance(risk.get("reasons"), list):
        risk["reasons"] = ["No reasons provided."]

    issues = raw.get("issues", [])
    if not isinstance(issues, list):
        issues = []

    valid_types = {"logic", "exception", "security", "performance", "maintainability", "test_missing", "rule_violation"}
    valid_severities = {"low", "medium", "high"}
    valid_confidences = {"low", "medium", "high"}

    normalized_issues: list[dict] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if issue.get("type") not in valid_types:
            issue["type"] = "maintainability"
        if issue.get("severity") not in valid_severities:
            issue["severity"] = "low"
        if issue.get("confidence") not in valid_confidences:
            issue["confidence"] = "medium"
        if not issue.get("title"):
            issue["title"] = "Unnamed issue"
        if not issue.get("description"):
            continue
        if not issue.get("suggestion"):
            issue["suggestion"] = "Review and consider improvements."
        matched = set(issue.get("matched_rule_ids") or [])
        matched = matched & rule_match_ids
        issue["matched_rule_ids"] = list(matched)
        normalized_issues.append(issue)

    raw["risk"] = risk
    raw["issues"] = normalized_issues
    return raw


def _persist_report(db: Session, task: ReviewTask, ai_result: dict, rule_match_ids: set[str]) -> None:
    validated = _validate_and_normalize_ai_output(ai_result, rule_match_ids)
    summary = validated.get("summary", {})
    risk = validated.get("risk", {})
    issues = validated.get("issues", [])

    summary_text = json.dumps(summary, ensure_ascii=False)

    report = ReviewReport(
        task_id=task.id,
        summary=summary_text,
        risk_level=RiskLevel(risk.get("level", "low")),
        risk_reasons=risk.get("reasons", []),
        issue_stats={
            "total": len(issues),
            "high": sum(1 for i in issues if i.get("severity") == "high"),
            "medium": sum(1 for i in issues if i.get("severity") == "medium"),
            "low": sum(1 for i in issues if i.get("severity") == "low"),
        },
        raw_ai_result=validated,
    )
    db.add(report)
    db.flush()

    for issue_data in issues:
        location = issue_data.get("location") or {}
        db_issue = ReviewIssue(
            task_id=task.id,
            report_id=report.id,
            title=issue_data.get("title", "Untitled"),
            issue_type=IssueType(issue_data.get("type", "maintainability")),
            severity=Severity(issue_data.get("severity", "low")),
            description=issue_data.get("description", ""),
            file_path=location.get("file_path"),
            line_hint=location.get("line_hint"),
            code_snippet=location.get("code_snippet"),
            suggestion=issue_data.get("suggestion", ""),
            confidence=Confidence(issue_data.get("confidence", "medium")),
            matched_rule_ids=issue_data.get("matched_rule_ids", []),
            feedback_status=FeedbackStatus.none,
        )
        db.add(db_issue)

    task.risk_level = report.risk_level
    task.issue_count = len(issues)


def _severity_sort_key(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 99)


def run_review_orchestrator(task_id: str, db_factory: callable | None = None) -> None:
    _get_db = db_factory if db_factory is not None else SessionLocal
    db = _get_db()
    try:
        task = db.scalar(select(ReviewTask).where(ReviewTask.id == task_id))
        if task is None:
            logger.error("Review task %s not found", task_id)
            return
        if task.status == TaskStatus.deleted:
            logger.info("Review task %s is deleted, skipping", task_id)
            return

        _process_task(db, task)
    except Exception:
        logger.exception("Orchestration failed for task %s", task_id)
        try:
            task = db.scalar(select(ReviewTask).where(ReviewTask.id == task_id))
            if task is not None:
                task.status = TaskStatus.failed
                task.error_message = "Internal error during review processing."
                db.commit()
        except Exception:
            logger.exception("Failed to persist error state for task %s", task_id)
    finally:
        db.close()


def _process_task(db: Session, task: ReviewTask) -> None:
    task.status = TaskStatus.running
    task.error_message = None
    db.commit()

    parsed = parse_diff(task.diff_content)
    rules = _load_enabled_rules(db, task.demo_owner)
    rule_matches = run_rule_engine(rules, parsed, task.diff_content)
    rule_match_ids = {m.rule_id for m in rule_matches}

    prompt = _build_prompt(task, parsed, rule_matches, rules)

    provider = create_llm_provider()
    logger.info("Calling LLM for task %s with %d files, %d rules, %d pre-matches",
                task.id, parsed.metrics.file_count, len(rules), len(rule_matches))

    try:
        ai_result = provider.generate_review(prompt)
    except LLMError:
        logger.exception("LLM call failed for task %s", task.id)
        task.status = TaskStatus.failed
        task.error_message = "LLM review generation failed."
        db.commit()
        return

    _persist_report(db, task, ai_result, rule_match_ids)
    task.status = TaskStatus.completed
    db.commit()
    logger.info("Review completed for task %s: %d issues, risk=%s", task.id, task.issue_count, task.risk_level)


def _load_enabled_rules(db: Session, demo_owner: str) -> list[ReviewRule]:
    return list(db.scalars(
        select(ReviewRule).where(
            ReviewRule.demo_owner == demo_owner,
            ReviewRule.enabled.is_(True),
            ReviewRule.deleted_at.is_(None),
        )
    ).all())
