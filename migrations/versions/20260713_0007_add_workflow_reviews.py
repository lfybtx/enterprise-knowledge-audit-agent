"""add workflow human review fields

Revision ID: 20260713_0007
Revises: 20260713_0006
Create Date: 2026-07-13 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260713_0007"
down_revision = "20260713_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="not_required"))
    op.add_column("workflow_runs", sa.Column("review_decision", sa.String(length=20), nullable=True))
    op.add_column("workflow_runs", sa.Column("reviewed_by", sa.String(length=100), nullable=True))
    op.add_column("workflow_runs", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column("workflow_runs", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("workflow_runs", "approval_status", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_runs", "reviewed_at")
    op.drop_column("workflow_runs", "review_comment")
    op.drop_column("workflow_runs", "reviewed_by")
    op.drop_column("workflow_runs", "review_decision")
    op.drop_column("workflow_runs", "approval_status")
