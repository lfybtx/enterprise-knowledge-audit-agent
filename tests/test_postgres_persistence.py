import os
from uuid import UUID, uuid4

import pytest


if not os.getenv("DATABASE_URL"):
    pytest.skip("Set DATABASE_URL to run PostgreSQL persistence tests", allow_module_level=True)

try:
    from app.db import get_session_factory
    from app.models import DocumentChunk, KnowledgeDocument
    from app.repositories.knowledge_repository import backfill_missing_embeddings, load_document_records, persist_document
except ModuleNotFoundError:
    pytest.skip("SQLAlchemy is not installed in this environment", allow_module_level=True)


def test_persisted_document_can_be_loaded_with_chunks():
    session = get_session_factory()()
    title = f"Persistence test {uuid4()}"
    document_id = None
    try:
        stored = persist_document(
            session,
            title=title,
            source="persistence-test.txt",
            file_type="txt",
            content="Regional manager approval is required before exporting a customer list.",
            chunks=[
                {
                    "text": "Regional manager approval is required before exporting a customer list.",
                    "location": {"kind": "lines", "start_line": 1, "end_line": 1},
                }
            ],
        )
        document_id = stored["id"]
        loaded = next(item for item in load_document_records(session) if item["id"] == stored["id"])

        assert loaded["title"] == title
        assert loaded["chunks"][0]["location"]["start_line"] == 1

        stored_chunk = document.chunks[0] if (document := session.get(KnowledgeDocument, UUID(document_id))) else None
        assert stored_chunk is not None
        assert stored_chunk.embedding is not None
    finally:
        if document_id:
            document = session.get(KnowledgeDocument, UUID(document_id))
            if document is not None:
                session.delete(document)
                session.commit()
        session.close()


def test_missing_chunk_embeddings_can_be_backfilled():
    session = get_session_factory()()
    title = f"Backfill test {uuid4()}"
    document_id = None
    try:
        stored = persist_document(
            session,
            title=title,
            source="backfill-test.txt",
            file_type="txt",
            content="Customer data export requires approval.",
            chunks=[
                {
                    "text": "Customer data export requires approval.",
                    "location": {"kind": "lines", "start_line": 1, "end_line": 1},
                }
            ],
        )
        document_id = stored["id"]
        document = session.get(KnowledgeDocument, UUID(document_id))
        assert document is not None
        chunk = document.chunks[0]
        session.execute(
            DocumentChunk.__table__.update().where(DocumentChunk.id == chunk.id).values(embedding=None)
        )
        session.commit()

        assert backfill_missing_embeddings(session) >= 1
        session.refresh(chunk)
        assert chunk.embedding is not None
    finally:
        if document_id:
            document = session.get(KnowledgeDocument, UUID(document_id))
            if document is not None:
                session.delete(document)
                session.commit()
        session.close()
