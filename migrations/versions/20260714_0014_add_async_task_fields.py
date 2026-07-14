"""add async task metadata"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260714_0014"
down_revision = "20260714_0013"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("index_tasks", sa.Column("duration_ms", sa.Integer()))
    op.add_column("index_tasks", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("index_tasks", sa.Column("payload", postgresql.JSONB()))
    op.add_column("index_tasks", sa.Column("result", postgresql.JSONB()))

def downgrade():
    op.drop_column("index_tasks", "result")
    op.drop_column("index_tasks", "payload")
    op.drop_column("index_tasks", "retry_count")
    op.drop_column("index_tasks", "duration_ms")
