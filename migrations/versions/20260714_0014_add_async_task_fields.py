"""add async task metadata"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260714_0014"
down_revision = "20260714_0013"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("index_tasks")}
    if "duration_ms" not in existing:
        op.add_column("index_tasks", sa.Column("duration_ms", sa.Integer()))
    if "retry_count" not in existing:
        op.add_column("index_tasks", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    if "payload" not in existing:
        op.add_column("index_tasks", sa.Column("payload", postgresql.JSONB()))
    if "result" not in existing:
        op.add_column("index_tasks", sa.Column("result", postgresql.JSONB()))

def downgrade():
    op.drop_column("index_tasks", "result")
    op.drop_column("index_tasks", "payload")
    op.drop_column("index_tasks", "retry_count")
    op.drop_column("index_tasks", "duration_ms")
