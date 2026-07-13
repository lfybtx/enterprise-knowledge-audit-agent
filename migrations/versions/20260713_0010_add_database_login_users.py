"""add database login users

Revision ID: 20260713_0010
Revises: 20260713_0009
Create Date: 2026-07-13 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260713_0010"
down_revision = "20260713_0009"
branch_labels = None
depends_on = None


ADMIN_HASH = "pbkdf2_sha256$120000$admin-seed-salt$hoKbCEH82Iw-KpBZKMasbb6qP3Iq-5c3543sm0u3lv4="
ALICE_HASH = "pbkdf2_sha256$120000$alice-seed-salt$hdtfvRdINnhUeobTFPLDSAeXt4hkATsOGSM38Idj3oA="
BOB_HASH = "pbkdf2_sha256$120000$bob-seed-salt$SPq2AvBdYeRU5OopUtLtH3fx5Iuqq47mHtY8sbvSN4Q="


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=False, server_default="user"))
    op.add_column("users", sa.Column("tenant_id", sa.String(length=100), nullable=False, server_default="tenant-demo"))
    op.add_column("users", sa.Column("department", sa.String(length=100), nullable=False, server_default="general"))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))

    op.execute("UPDATE users SET username = external_id WHERE username IS NULL")
    op.execute("UPDATE users SET password_hash = 'pbkdf2_sha256$120000$legacy-disabled$disabled' WHERE password_hash IS NULL")
    op.execute("UPDATE users SET username = 'alice', password_hash = '%s', department = 'sales' WHERE external_id = 'demo-alice'" % ALICE_HASH)
    op.execute("UPDATE users SET username = 'bob', password_hash = '%s', department = 'legal' WHERE external_id = 'demo-bob'" % BOB_HASH)
    op.execute("UPDATE users SET username = 'local-demo', password_hash = '%s', department = 'compliance' WHERE external_id = 'local-demo'" % ADMIN_HASH)

    op.execute(
        """
        INSERT INTO users (external_id, username, password_hash, display_name, role, tenant_id, department, is_active)
        VALUES ('admin', 'admin', '%s', 'Admin', 'admin', 'tenant-demo', 'platform', true)
        ON CONFLICT (external_id) DO NOTHING
        """
        % ADMIN_HASH
    )

    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)
    op.create_unique_constraint(op.f("uq_users_username"), "users", ["username"])
    op.create_check_constraint("ck_users_role", "users", "role IN ('admin', 'user')")


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    op.drop_column("users", "is_active")
    op.drop_column("users", "department")
    op.drop_column("users", "tenant_id")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
