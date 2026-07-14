"""Store human-corrected audit findings."""
from alembic import op
import sqlalchemy as sa

revision = "20260714_0013"
down_revision = "20260714_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("reviewed_findings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_runs", "reviewed_findings")
