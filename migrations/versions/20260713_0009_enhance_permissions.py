"""enhance knowledge base and document permissions

Revision ID: 20260713_0009
Revises: 20260713_0008
Create Date: 2026-07-13 21:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260713_0009"
down_revision = "20260713_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_bases", sa.Column("tenant_id", sa.String(length=100), nullable=False, server_default="tenant-demo"))
    op.add_column("knowledge_bases", sa.Column("department", sa.String(length=100), nullable=False, server_default="general"))
    op.add_column("knowledge_bases", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.alter_column("knowledge_bases", "tenant_id", server_default=None)
    op.alter_column("knowledge_bases", "department", server_default=None)
    op.alter_column("knowledge_bases", "description", server_default=None)

    op.create_table(
        "document_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_permissions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_document_permissions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_permissions")),
        sa.UniqueConstraint("document_id", "user_id", name=op.f("uq_document_permissions_document_id")),
    )
    op.create_index(op.f("ix_document_permissions_document_id"), "document_permissions", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_permissions_user_id"), "document_permissions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_permissions_user_id"), table_name="document_permissions")
    op.drop_index(op.f("ix_document_permissions_document_id"), table_name="document_permissions")
    op.drop_table("document_permissions")
    op.drop_column("knowledge_bases", "description")
    op.drop_column("knowledge_bases", "department")
    op.drop_column("knowledge_bases", "tenant_id")
