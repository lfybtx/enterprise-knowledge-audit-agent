"""store structured trace data

Revision ID: 20260713_0006
Revises: 20260713_0005
Create Date: 2026-07-13 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260713_0006"
down_revision = "20260713_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_trace_steps",
        sa.Column("trace_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.alter_column("workflow_trace_steps", "trace_data", server_default=None)


def downgrade() -> None:
    op.drop_column("workflow_trace_steps", "trace_data")
