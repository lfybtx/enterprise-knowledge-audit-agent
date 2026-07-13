"""remove legacy demo users

Revision ID: 20260714_0011
Revises: 20260713_0010
Create Date: 2026-07-14 10:30:00.000000
"""

from alembic import op


revision = "20260714_0011"
down_revision = "20260713_0010"
branch_labels = None
depends_on = None


DEMO_USER_IDS = "'local-demo', 'demo-alice', 'demo-bob'"


def upgrade() -> None:
    # Preserve existing knowledge bases by transferring their ownership and
    # membership to the real administrator before removing demo identities.
    op.execute(f"UPDATE knowledge_bases SET owner_id = 'admin' WHERE owner_id IN ({DEMO_USER_IDS})")
    op.execute(
        """
        INSERT INTO knowledge_base_members (knowledge_base_id, user_id, role)
        SELECT kb.id, admin_user.id, 'owner'
        FROM knowledge_bases kb
        JOIN users admin_user ON admin_user.external_id = 'admin'
        ON CONFLICT (knowledge_base_id, user_id) DO UPDATE SET role = EXCLUDED.role
        """
    )
    op.execute(f"DELETE FROM users WHERE external_id IN ({DEMO_USER_IDS})")


def downgrade() -> None:
    # Demo accounts are intentionally not restored because their credentials
    # must not be reintroduced by a schema rollback.
    pass
