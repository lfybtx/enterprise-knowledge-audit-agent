"""add vector embeddings to document chunks

Revision ID: 20260712_0002
Revises: 20260712_0001
Create Date: 2026-07-12 00:00:00
"""

from alembic import op


revision = "20260712_0002"
down_revision = "20260712_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(64)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_cosine "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_cosine")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
