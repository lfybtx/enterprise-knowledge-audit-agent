"""expand workflow trace id length

Revision ID: 20260713_0008
Revises: 20260713_0007
Create Date: 2026-07-13 00:08:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260713_0008"
down_revision = "20260713_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("workflow_runs", "trace_id", existing_type=sa.String(length=36), type_=sa.String(length=80))


def downgrade() -> None:
    op.alter_column("workflow_runs", "trace_id", existing_type=sa.String(length=80), type_=sa.String(length=36))
