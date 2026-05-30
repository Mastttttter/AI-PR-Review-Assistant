"""add pr_url to review_tasks

Revision ID: 3134f36008b3
Revises: 20260529_0001
Create Date: 2026-05-30 22:17:46.459412
"""
from alembic import op
import sqlalchemy as sa


revision = '3134f36008b3'
down_revision = '20260529_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('review_tasks', sa.Column('pr_url', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column('review_tasks', 'pr_url')
