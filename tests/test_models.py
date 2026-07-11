import pytest


sqlalchemy = pytest.importorskip("sqlalchemy")

from app.db import Base
from app.models import DocumentChunk, KnowledgeBase, KnowledgeDocument


def test_database_models_define_core_tables():
    assert {"knowledge_bases", "documents", "document_chunks"} <= set(Base.metadata.tables)
    assert KnowledgeBase.__tablename__ == "knowledge_bases"
    assert KnowledgeDocument.__tablename__ == "documents"
    assert DocumentChunk.__tablename__ == "document_chunks"


def test_document_chunk_has_unique_document_index_constraint():
    constraints = DocumentChunk.__table__.constraints
    assert any(
        getattr(constraint, "columns", None)
        and {column.name for column in constraint.columns} == {"document_id", "chunk_index"}
        for constraint in constraints
    )
