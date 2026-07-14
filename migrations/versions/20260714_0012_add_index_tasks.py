"""add index task tracking"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260714_0012"
down_revision = "20260714_0011"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "index_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_index_tasks_document_id", "index_tasks", ["document_id"])

def downgrade():
    op.drop_index("ix_index_tasks_document_id", table_name="index_tasks")
    op.drop_table("index_tasks")
