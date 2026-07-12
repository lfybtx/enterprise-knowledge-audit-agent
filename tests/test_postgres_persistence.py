import os
from uuid import UUID, uuid4

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import select


if not os.getenv("DATABASE_URL"):
    pytest.skip("Set DATABASE_URL to run PostgreSQL persistence tests", allow_module_level=True)

try:
    from app.db import get_session_factory
    from app.models import DocumentChunk, KnowledgeDocument, WorkflowRun, WorkflowTraceStep
    from app.repositories.knowledge_repository import (
        backfill_missing_embeddings,
        load_audit_event_records,
        load_document_records,
        load_workflow_trace_records,
        persist_document,
        persist_workflow_run,
    )
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
        session.execute(DocumentChunk.__table__.update().where(DocumentChunk.id == chunk.id).values(embedding=None))
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


def test_workflow_trace_can_be_persisted_and_loaded():
    session = get_session_factory()()
    trace_id = f"trace-{uuid4()}"
    run_id = None
    try:
        stored = persist_workflow_run(
            session,
            trace_id=trace_id,
            user_external_id="demo-alice",
            event_type="question_answered",
            question="Can customer data be exported?",
            status="completed",
            duration_ms=123,
            step_count=2,
            summary="Customer export requires approval.",
            workflow_trace=[
                {
                    "name": "retrieval_agent",
                    "status": "completed",
                    "detail": "retrieved 1 evidence chunk",
                    "duration_ms": 12,
                    "prompt": "Question: Can customer data be exported?",
                    "tool_calls": ["evidence_loader"],
                    "input_tokens": 10,
                    "output_tokens": 24,
                    "failure_reason": None,
                },
                {
                    "name": "audit_agent",
                    "status": "completed",
                    "detail": "generated 1 finding",
                    "duration_ms": 23,
                    "prompt": "Question: Can customer data be exported?",
                    "tool_calls": ["assess"],
                    "input_tokens": 12,
                    "output_tokens": 36,
                    "failure_reason": None,
                },
            ],
        )
        run_id = stored["id"]

        loaded = load_workflow_trace_records(session, trace_id)
        audit_events = load_audit_event_records(session, "demo-alice")

        assert stored["trace_id"] == trace_id
        assert loaded is not None
        assert loaded["workflow_trace"][0]["name"] == "retrieval_agent"
        assert loaded["workflow_trace"][1]["tool_calls"] == ["assess"]
        assert any(item["trace_id"] == trace_id for item in audit_events)
    finally:
        if run_id is not None:
            run = session.get(WorkflowRun, run_id)
            if run is not None:
                session.delete(run)
                session.commit()
        session.close()
