"""add users and knowledge base memberships

Revision ID: 20260712_0003
Revises: 20260712_0002
Create Date: 2026-07-12 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260712_0003"
down_revision = "20260712_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("external_id", name=op.f("uq_users_external_id")),
    )
    op.create_table(
        "knowledge_base_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_knowledge_base_members_role",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_knowledge_base_members_knowledge_base_id_knowledge_bases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_base_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_base_members")),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "user_id",
            name=op.f("uq_knowledge_base_members_knowledge_base_id"),
        ),
    )
    op.create_index(
        op.f("ix_knowledge_base_members_knowledge_base_id"),
        "knowledge_base_members",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_base_members_user_id"),
        "knowledge_base_members",
        ["user_id"],
        unique=False,
    )

    # Preserve access to data created before membership-based authorization.
    op.execute(
        """
        INSERT INTO users (external_id, display_name)
        SELECT DISTINCT owner_id, owner_id
        FROM knowledge_bases
        ON CONFLICT (external_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO knowledge_base_members (knowledge_base_id, user_id, role)
        SELECT knowledge_bases.id, users.id, 'owner'
        FROM knowledge_bases
        JOIN users ON users.external_id = knowledge_bases.owner_id
        ON CONFLICT (knowledge_base_id, user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_base_members_user_id"), table_name="knowledge_base_members")
    op.drop_index(op.f("ix_knowledge_base_members_knowledge_base_id"), table_name="knowledge_base_members")
    op.drop_table("knowledge_base_members")
    op.drop_table("users")
