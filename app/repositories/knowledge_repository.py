from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models import DocumentChunk, KnowledgeBase, KnowledgeDocument


LOCAL_KNOWLEDGE_BASE_NAME = "Local demo knowledge base"
LOCAL_OWNER_ID = "local-demo"


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot be used for an application request."""


def ensure_local_knowledge_base(session: Session) -> KnowledgeBase:
    knowledge_base = session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.name == LOCAL_KNOWLEDGE_BASE_NAME,
            KnowledgeBase.owner_id == LOCAL_OWNER_ID,
        )
    )
    if knowledge_base is None:
        knowledge_base = KnowledgeBase(name=LOCAL_KNOWLEDGE_BASE_NAME, owner_id=LOCAL_OWNER_ID)
        session.add(knowledge_base)
        session.flush()
    return knowledge_base


def persist_document(
    session: Session,
    *,
    title: str,
    source: str,
    file_type: str,
    content: str,
    chunks: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Store one parsed document and all of its retrievable chunks atomically."""
    try:
        knowledge_base = ensure_local_knowledge_base(session)
        document = KnowledgeDocument(
            knowledge_base_id=knowledge_base.id,
            title=title,
            source=source,
            file_type=file_type,
            content=content,
        )
        session.add(document)
        session.flush()

        for chunk_index, chunk in enumerate(chunks, start=1):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    text=str(chunk["text"]),
                    location=dict(chunk.get("location", {"kind": "document"})),
                )
            )

        session.commit()
        session.refresh(document)
        return document_to_record(document)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its schema has not been migrated") from exc


def load_document_records(session: Session) -> list[dict[str, Any]]:
    """Load persisted documents in the shape expected by the local retriever."""
    try:
        documents = session.scalars(
            select(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.chunks))
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        ).all()
        return [document_to_record(document) for document in documents]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its schema has not been migrated") from exc


def list_document_summaries(session: Session) -> list[dict[str, Any]]:
    try:
        chunk_count = func.count(DocumentChunk.id).label("chunk_count")
        rows = session.execute(
            select(
                KnowledgeDocument.id,
                KnowledgeDocument.title,
                KnowledgeDocument.source,
                chunk_count,
            )
            .outerjoin(DocumentChunk)
            .group_by(KnowledgeDocument.id)
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        ).all()
        return [
            {
                "id": str(row.id),
                "title": row.title,
                "source": row.source,
                "chunk_count": row.chunk_count,
            }
            for row in rows
        ]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its schema has not been migrated") from exc


def database_is_ready(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        session.rollback()
        return False


def document_to_record(document: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "title": document.title,
        "source": document.source,
        "file_type": document.file_type,
        "content": document.content,
        "chunks": [
            {
                "id": str(chunk.id),
                "text": chunk.text,
                "location": chunk.location,
            }
            for chunk in sorted(document.chunks, key=lambda item: item.chunk_index)
        ],
    }
