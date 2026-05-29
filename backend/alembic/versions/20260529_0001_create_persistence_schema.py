"""create persistence schema

Revision ID: 20260529_0001
Revises:
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "20260529_0001"
down_revision = None
branch_labels = None
depends_on = None

TASK_STATUSES = "'pending', 'running', 'completed', 'failed', 'deleted'"
RISK_LEVELS = "'low', 'medium', 'high'"
ISSUE_TYPES = "'logic', 'exception', 'security', 'performance', 'maintainability', 'test_missing', 'rule_violation'"
FEEDBACK_STATUSES = "'none', 'useful', 'useless', 'false_positive', 'adopted', 'ignored'"
RULE_TYPES = "'test', 'style', 'security', 'documentation', 'naming', 'module'"


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pr_title", sa.String(length=255), nullable=False),
        sa.Column("pr_description", sa.Text(), nullable=True),
        sa.Column("project_name", sa.String(length=255), nullable=True),
        sa.Column("target_branch", sa.String(length=255), nullable=True),
        sa.Column("developer_name", sa.String(length=255), nullable=True),
        sa.Column("demo_owner", sa.String(length=255), nullable=False),
        sa.Column("diff_content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("length(diff_content) <= 50000", name="ck_review_tasks_diff_content_max_50000"),
        sa.CheckConstraint(f"status IN ({TASK_STATUSES})", name="ck_review_tasks_status_values"),
        sa.CheckConstraint(f"risk_level IS NULL OR risk_level IN ({RISK_LEVELS})", name="ck_review_tasks_risk_level_values"),
        sa.PrimaryKeyConstraint("id", name="pk_review_tasks"),
    )
    op.create_index("ix_review_tasks_demo_owner", "review_tasks", ["demo_owner"])
    op.create_index("ix_review_tasks_demo_owner_created_at", "review_tasks", ["demo_owner", "created_at"])

    op.create_table(
        "review_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("risk_reasons", sa.JSON(), nullable=False),
        sa.Column("issue_stats", sa.JSON(), nullable=False),
        sa.Column("raw_ai_result", sa.JSON(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(f"risk_level IN ({RISK_LEVELS})", name="ck_review_reports_risk_level_values"),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], name="fk_review_reports_task_id_review_tasks"),
        sa.PrimaryKeyConstraint("id", name="pk_review_reports"),
        sa.UniqueConstraint("task_id", name="uq_review_reports_task_id"),
    )
    op.create_index("ix_review_reports_task_id", "review_reports", ["task_id"])

    op.create_table(
        "review_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("demo_owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(f"rule_type IN ({RULE_TYPES})", name="ck_review_rules_rule_type_values"),
        sa.CheckConstraint(f"severity IN ({RISK_LEVELS})", name="ck_review_rules_severity_values"),
        sa.PrimaryKeyConstraint("id", name="pk_review_rules"),
    )
    op.create_index("ix_review_rules_demo_owner", "review_rules", ["demo_owner"])
    op.create_index("ix_review_rules_enabled_type", "review_rules", ["enabled", "rule_type"])

    op.create_table(
        "review_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("line_hint", sa.String(length=255), nullable=True),
        sa.Column("code_snippet", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("matched_rule_ids", sa.JSON(), nullable=False),
        sa.Column("feedback_status", sa.String(length=32), nullable=False),
        *timestamps(),
        sa.CheckConstraint(f"issue_type IN ({ISSUE_TYPES})", name="ck_review_issues_issue_type_values"),
        sa.CheckConstraint(f"severity IN ({RISK_LEVELS})", name="ck_review_issues_severity_values"),
        sa.CheckConstraint(f"confidence IN ({RISK_LEVELS})", name="ck_review_issues_confidence_values"),
        sa.CheckConstraint(f"feedback_status IN ({FEEDBACK_STATUSES})", name="ck_review_issues_feedback_status_values"),
        sa.ForeignKeyConstraint(["report_id"], ["review_reports.id"], name="fk_review_issues_report_id_review_reports"),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], name="fk_review_issues_task_id_review_tasks"),
        sa.PrimaryKeyConstraint("id", name="pk_review_issues"),
    )
    op.create_index("ix_review_issues_report_id", "review_issues", ["report_id"])
    op.create_index("ix_review_issues_task_id", "review_issues", ["task_id"])
    op.create_index("ix_review_issues_task_severity", "review_issues", ["task_id", "severity"])

    op.create_table(
        "issue_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("demo_owner", sa.String(length=255), nullable=False),
        sa.Column("feedback_status", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(f"feedback_status IN ({FEEDBACK_STATUSES})", name="ck_issue_feedback_feedback_status_values"),
        sa.ForeignKeyConstraint(["issue_id"], ["review_issues.id"], name="fk_issue_feedback_issue_id_review_issues"),
        sa.ForeignKeyConstraint(["task_id"], ["review_tasks.id"], name="fk_issue_feedback_task_id_review_tasks"),
        sa.PrimaryKeyConstraint("id", name="pk_issue_feedback"),
    )
    op.create_index("ix_issue_feedback_demo_owner", "issue_feedback", ["demo_owner"])
    op.create_index("ix_issue_feedback_issue_created_at", "issue_feedback", ["issue_id", "created_at"])
    op.create_index("ix_issue_feedback_issue_id", "issue_feedback", ["issue_id"])
    op.create_index("ix_issue_feedback_task_id", "issue_feedback", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_issue_feedback_task_id", table_name="issue_feedback")
    op.drop_index("ix_issue_feedback_issue_id", table_name="issue_feedback")
    op.drop_index("ix_issue_feedback_issue_created_at", table_name="issue_feedback")
    op.drop_index("ix_issue_feedback_demo_owner", table_name="issue_feedback")
    op.drop_table("issue_feedback")
    op.drop_index("ix_review_issues_task_severity", table_name="review_issues")
    op.drop_index("ix_review_issues_task_id", table_name="review_issues")
    op.drop_index("ix_review_issues_report_id", table_name="review_issues")
    op.drop_table("review_issues")
    op.drop_index("ix_review_rules_enabled_type", table_name="review_rules")
    op.drop_index("ix_review_rules_demo_owner", table_name="review_rules")
    op.drop_table("review_rules")
    op.drop_index("ix_review_reports_task_id", table_name="review_reports")
    op.drop_table("review_reports")
    op.drop_index("ix_review_tasks_demo_owner_created_at", table_name="review_tasks")
    op.drop_index("ix_review_tasks_demo_owner", table_name="review_tasks")
    op.drop_table("review_tasks")
