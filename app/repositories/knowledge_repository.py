from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models import DocumentChunk, KnowledgeBase, KnowledgeBaseMember, KnowledgeDocument, User
from app.services.embeddings import embed_text
from app.services.retrieval import HybridRetriever, RetrievedChunk
from app.vector_utils import vector_literal


LOCAL_KNOWLEDGE_BASE_NAME = "Local demo knowledge base"
LOCAL_OWNER_ID = "local-demo"
WRITE_ROLES = {"owner", "editor"}


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot be used for an application request."""


def ensure_user(session: Session, external_id: str, display_name: str | None = None) -> User:
    user = session.scalar(select(User).where(User.external_id == external_id))
    if user is None:
        user = User(external_id=external_id, display_name=display_name or external_id)
        session.add(user)
        session.flush()
    return user


def ensure_knowledge_base_membership(
    session: Session,
    *,
    knowledge_base: KnowledgeBase,
    user: User,
    role: str,
) -> KnowledgeBaseMember:
    membership = session.scalar(
        select(KnowledgeBaseMember).where(
            KnowledgeBaseMember.knowledge_base_id == knowledge_base.id,
            KnowledgeBaseMember.user_id == user.id,
        )
    )
    if membership is None:
        membership = KnowledgeBaseMember(knowledge_base_id=knowledge_base.id, user_id=user.id, role=role)
        session.add(membership)
        session.flush()
    return membership


def ensure_local_knowledge_base(session: Session, owner_external_id: str = LOCAL_OWNER_ID) -> KnowledgeBase:
    knowledge_base = session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.name == LOCAL_KNOWLEDGE_BASE_NAME,
            KnowledgeBase.owner_id == owner_external_id,
        )
    )
    if knowledge_base is None:
        knowledge_base = KnowledgeBase(name=LOCAL_KNOWLEDGE_BASE_NAME, owner_id=owner_external_id)
        session.add(knowledge_base)
        session.flush()
    user = ensure_user(session, owner_external_id)
    ensure_knowledge_base_membership(session, knowledge_base=knowledge_base, user=user, role="owner")
    return knowledge_base


def user_can_write_knowledge_base(session: Session, user_external_id: str, knowledge_base_id: UUID) -> bool:
    role = session.scalar(
        select(KnowledgeBaseMember.role)
        .join(User, User.id == KnowledgeBaseMember.user_id)
        .where(
            KnowledgeBaseMember.knowledge_base_id == knowledge_base_id,
            User.external_id == user_external_id,
        )
    )
    return role in WRITE_ROLES


def persist_document(
    session: Session,
    *,
    user_external_id: str = LOCAL_OWNER_ID,
    title: str,
    source: str,
    file_type: str,
    content: str,
    chunks: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Store one parsed document and all of its retrievable chunks atomically."""
    try:
        knowledge_base = ensure_local_knowledge_base(session, user_external_id)
        if not user_can_write_knowledge_base(session, user_external_id, knowledge_base.id):
            raise DatabaseUnavailableError("Current user cannot write to this knowledge base")
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
            chunk_text = str(chunk["text"])
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    location=dict(chunk.get("location", {"kind": "document"})),
                    embedding=embed_text(chunk_text),
                )
            )

        session.commit()
        session.refresh(document)
        return document_to_record(document)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its schema has not been migrated") from exc


def load_document_records(session: Session, user_external_id: str | None = None) -> list[dict[str, Any]]:
    """Load persisted documents in the shape expected by the local retriever."""
    try:
        backfill_missing_embeddings(session)
        statement = (
            select(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.chunks), selectinload(KnowledgeDocument.knowledge_base))
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        )
        if user_external_id is not None:
            statement = (
                statement.join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id)
                .join(KnowledgeBaseMember, KnowledgeBaseMember.knowledge_base_id == KnowledgeBase.id)
                .join(User, User.id == KnowledgeBaseMember.user_id)
                .where(User.external_id == user_external_id)
            )
        documents = session.scalars(statement).all()
        return [document_to_record(document) for document in documents]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its schema has not been migrated") from exc


def backfill_missing_embeddings(session: Session, batch_size: int = 100) -> int:
    """Populate embeddings for chunks created before the vector migration."""
    try:
        chunks = session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.embedding.is_(None))
            .order_by(DocumentChunk.created_at, DocumentChunk.id)
            .limit(batch_size)
        ).all()
        for chunk in chunks:
            chunk.embedding = embed_text(chunk.text)
        if chunks:
            session.commit()
        return len(chunks)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to backfill chunk embeddings") from exc


def list_document_summaries(session: Session, user_external_id: str | None = None) -> list[dict[str, Any]]:
    try:
        chunk_count = func.count(DocumentChunk.id).label("chunk_count")
        statement = (
            select(
                KnowledgeDocument.id,
                KnowledgeDocument.title,
                KnowledgeDocument.source,
                chunk_count,
            )
            .outerjoin(DocumentChunk)
            .group_by(KnowledgeDocument.id)
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        )
        if user_external_id is not None:
            statement = (
                statement.join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id)
                .join(KnowledgeBaseMember, KnowledgeBaseMember.knowledge_base_id == KnowledgeBase.id)
                .join(User, User.id == KnowledgeBaseMember.user_id)
                .where(User.external_id == user_external_id)
            )
        rows = session.execute(statement).all()
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


def hybrid_search_chunks(
    session: Session,
    question: str,
    limit: int = 3,
    user_external_id: str | None = None,
) -> list[RetrievedChunk]:
    """Search persisted chunks with lexical scoring plus pgvector cosine similarity."""
    try:
        documents = load_document_records(session, user_external_id)
        lexical_hits = HybridRetriever(documents).search(question, limit=limit * 4)
        semantic_hits = semantic_search_chunks(session, question, limit=limit * 4, user_external_id=user_external_id)
        return merge_search_results(lexical_hits, semantic_hits, limit)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL vector search is unavailable") from exc


def semantic_search_chunks(
    session: Session,
    question: str,
    limit: int = 12,
    user_external_id: str | None = None,
) -> list[RetrievedChunk]:
    embedding = vector_literal(embed_text(question))
    membership_join = ""
    membership_filter = ""
    params: dict[str, Any] = {"embedding": embedding, "limit": limit}
    if user_external_id is not None:
        membership_join = """
            JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
            JOIN knowledge_base_members kbm ON kbm.knowledge_base_id = kb.id
            JOIN users u ON u.id = kbm.user_id
        """
        membership_filter = "AND u.external_id = :user_external_id"
        params["user_external_id"] = user_external_id
    rows = session.execute(
        text(
            f"""
            SELECT
                dc.id::text AS chunk_id,
                d.id::text AS document_id,
                d.title AS title,
                d.source AS source,
                dc.text AS text,
                dc.location AS location,
                1 - (dc.embedding <=> CAST(:embedding AS vector)) AS score
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            {membership_join}
            WHERE dc.embedding IS NOT NULL
            {membership_filter}
            ORDER BY dc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            title=row["title"],
            source=row["source"],
            text=row["text"],
            location=dict(row["location"]),
            score=round(float(row["score"] or 0.0), 4),
        )
        for row in rows
    ]


def merge_search_results(
    lexical_hits: list[RetrievedChunk],
    semantic_hits: list[RetrievedChunk],
    limit: int,
) -> list[RetrievedChunk]:
    max_lexical_score = max((hit.score for hit in lexical_hits), default=0.0) or 1.0
    merged: dict[str, tuple[RetrievedChunk, float, float]] = {}

    for hit in lexical_hits:
        merged[hit.chunk_id] = (hit, hit.score / max_lexical_score, 0.0)
    for hit in semantic_hits:
        existing = merged.get(hit.chunk_id)
        if existing is None:
            merged[hit.chunk_id] = (hit, 0.0, max(0.0, hit.score))
        else:
            merged[hit.chunk_id] = (existing[0], existing[1], max(0.0, hit.score))

    ranked = []
    for hit, lexical_score, semantic_score in merged.values():
        combined_score = 0.55 * lexical_score + 0.45 * semantic_score
        ranked.append(
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                title=hit.title,
                source=hit.source,
                text=hit.text,
                location=hit.location,
                score=round(combined_score, 4),
            )
        )
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]


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
        "owner_id": document.knowledge_base.owner_id if document.knowledge_base else LOCAL_OWNER_ID,
        "chunks": [
            {
                "id": str(chunk.id),
                "text": chunk.text,
                "location": chunk.location,
            }
            for chunk in sorted(document.chunks, key=lambda item: item.chunk_index)
        ],
    }
