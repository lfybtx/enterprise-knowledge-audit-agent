from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DocumentPermission,
    DocumentChunk,
    KnowledgeBase,
    KnowledgeBaseMember,
    KnowledgeDocument,
    User,
    WorkflowRun,
    WorkflowTraceStep,
)
from app.services.embeddings import embed_query, embed_text, embed_texts
from app.services.auth import hash_password, verify_password
from app.services.reranking import rerank_candidates
from app.services.retrieval import HybridRetriever, RetrievedChunk
from app.vector_utils import vector_literal


LOCAL_KNOWLEDGE_BASE_NAME = "Local demo knowledge base"
LOCAL_OWNER_ID = "local-demo"
WRITE_ROLES = {"owner", "editor"}
MANAGE_ROLES = {"owner"}


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot be used for an application request."""


class WorkflowReviewError(RuntimeError):
    """Raised when a workflow review cannot be applied."""


def ensure_user(session: Session, external_id: str, display_name: str | None = None) -> User:
    user = session.scalar(select(User).where(User.external_id == external_id))
    if user is None:
        user = User(
            external_id=external_id,
            username=external_id,
            password_hash=hash_password("disabled-login"),
            display_name=display_name or external_id,
            role="user",
        )
        session.add(user)
        session.flush()
    return user


def user_to_record(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "external_id": user.external_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "department": user.department,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def auth_account_record(user: User) -> dict[str, Any]:
    return {
        "user_id": user.external_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "department": user.department,
    }


def authenticate_database_user(session: Session, username: str, password: str) -> dict[str, Any] | None:
    try:
        user = session.scalar(select(User).where(User.username == username.strip()))
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return auth_account_record(user)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to authenticate database user") from exc


def get_user_account(session: Session, external_id: str) -> dict[str, Any] | None:
    try:
        user = session.scalar(select(User).where(User.external_id == external_id, User.is_active.is_(True)))
        return auth_account_record(user) if user is not None else None
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to load user account") from exc


def list_user_records(session: Session) -> list[dict[str, Any]]:
    try:
        users = session.scalars(select(User).order_by(User.created_at, User.username)).all()
        return [user_to_record(user) for user in users]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to list users") from exc


def create_user_record(
    session: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    role: str = "user",
    tenant_id: str = "tenant-demo",
    department: str = "general",
) -> dict[str, Any]:
    if role not in {"admin", "user"}:
        raise ValueError("Invalid user role")
    normalized = username.strip()
    if session.scalar(select(User.id).where(User.username == normalized)) is not None:
        raise ValueError("Username already exists")
    if session.scalar(select(User.id).where(User.external_id == normalized)) is not None:
        raise ValueError("User id already exists")
    try:
        user = User(
            external_id=normalized,
            username=normalized,
            password_hash=hash_password(password),
            display_name=display_name,
            role=role,
            tenant_id=tenant_id,
            department=department,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user_to_record(user)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to create user") from exc


def update_user_record(
    session: Session,
    *,
    external_id: str,
    display_name: str | None = None,
    role: str | None = None,
    tenant_id: str | None = None,
    department: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    try:
        user = session.scalar(select(User).where(User.external_id == external_id))
        if user is None:
            raise ValueError("User was not found")
        if role is not None:
            if role not in {"admin", "user"}:
                raise ValueError("Invalid user role")
            user.role = role
        if display_name is not None:
            user.display_name = display_name
        if tenant_id is not None:
            user.tenant_id = tenant_id
        if department is not None:
            user.department = department
        if is_active is not None:
            user.is_active = is_active
        session.commit()
        session.refresh(user)
        return user_to_record(user)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to update user") from exc


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


def create_knowledge_base(
    session: Session,
    *,
    name: str,
    owner_external_id: str,
    tenant_id: str,
    department: str,
    description: str = "",
) -> dict[str, Any]:
    try:
        owner = ensure_user(session, owner_external_id)
        knowledge_base = KnowledgeBase(
            name=name,
            owner_id=owner_external_id,
            tenant_id=tenant_id,
            department=department,
            description=description,
        )
        session.add(knowledge_base)
        session.flush()
        ensure_knowledge_base_membership(session, knowledge_base=knowledge_base, user=owner, role="owner")
        session.commit()
        session.refresh(knowledge_base)
        return knowledge_base_to_record(knowledge_base, "owner")
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to create knowledge base") from exc


def list_knowledge_base_records(session: Session, user_external_id: str) -> list[dict[str, Any]]:
    try:
        if is_admin_user(session, user_external_id):
            knowledge_bases = session.scalars(
                select(KnowledgeBase).order_by(KnowledgeBase.created_at, KnowledgeBase.name)
            ).all()
            return [knowledge_base_to_record(knowledge_base, "admin") for knowledge_base in knowledge_bases]
        rows = session.execute(
            select(KnowledgeBase, KnowledgeBaseMember.role)
            .join(KnowledgeBaseMember, KnowledgeBaseMember.knowledge_base_id == KnowledgeBase.id)
            .join(User, User.id == KnowledgeBaseMember.user_id)
            .where(User.external_id == user_external_id)
            .order_by(KnowledgeBase.created_at, KnowledgeBase.name)
        ).all()
        return [knowledge_base_to_record(knowledge_base, role) for knowledge_base, role in rows]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to list knowledge bases") from exc


def list_knowledge_base_members(session: Session, knowledge_base_id: UUID, user_external_id: str) -> list[dict[str, Any]]:
    if not user_can_view_knowledge_base(session, user_external_id, knowledge_base_id):
        raise PermissionError("Current user cannot view this knowledge base")
    try:
        rows = session.execute(
            select(KnowledgeBaseMember, User)
            .join(User, User.id == KnowledgeBaseMember.user_id)
            .where(KnowledgeBaseMember.knowledge_base_id == knowledge_base_id)
            .order_by(KnowledgeBaseMember.role, User.external_id)
        ).all()
        return [
            {
                "user_id": user.external_id,
                "display_name": user.display_name,
                "role": membership.role,
                "created_at": membership.created_at.isoformat() if membership.created_at else None,
            }
            for membership, user in rows
        ]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to list knowledge base members") from exc


def upsert_knowledge_base_member(
    session: Session,
    *,
    knowledge_base_id: UUID,
    actor_external_id: str,
    member_external_id: str,
    role: str,
) -> dict[str, Any]:
    if role not in {"owner", "editor", "viewer"}:
        raise ValueError("Invalid role")
    if role == "owner" and not is_admin_user(session, actor_external_id):
        raise PermissionError("Only admin can assign owner role")
    if not user_can_manage_knowledge_base(session, actor_external_id, knowledge_base_id):
        raise PermissionError("Current user cannot manage this knowledge base")
    try:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None:
            raise PermissionError("Knowledge base was not found")
        user = session.scalar(select(User).where(User.external_id == member_external_id, User.is_active.is_(True)))
        if user is None:
            raise ValueError("Member must be an active database user")
        membership = ensure_knowledge_base_membership(session, knowledge_base=knowledge_base, user=user, role=role)
        membership.role = role
        session.commit()
        return {"user_id": user.external_id, "display_name": user.display_name, "role": membership.role}
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to save knowledge base member") from exc


def remove_knowledge_base_member(
    session: Session,
    *,
    knowledge_base_id: UUID,
    actor_external_id: str,
    member_external_id: str,
) -> None:
    if actor_external_id == member_external_id:
        raise PermissionError("You cannot remove yourself from a knowledge base")
    if not is_admin_user(session, actor_external_id):
        raise PermissionError("Only admin can remove knowledge base members")
    if not user_can_manage_knowledge_base(session, actor_external_id, knowledge_base_id):
        raise PermissionError("Current user cannot manage this knowledge base")
    try:
        membership = session.scalar(
            select(KnowledgeBaseMember)
            .join(User, User.id == KnowledgeBaseMember.user_id)
            .where(
                KnowledgeBaseMember.knowledge_base_id == knowledge_base_id,
                User.external_id == member_external_id,
            )
        )
        if membership is not None:
            session.delete(membership)
            session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to remove knowledge base member") from exc


def user_can_view_knowledge_base(session: Session, user_external_id: str, knowledge_base_id: UUID) -> bool:
    if is_admin_user(session, user_external_id):
        return True
    return _user_role_for_knowledge_base(session, user_external_id, knowledge_base_id) is not None


def user_can_write_knowledge_base(session: Session, user_external_id: str, knowledge_base_id: UUID) -> bool:
    if is_admin_user(session, user_external_id):
        return True
    return _user_role_for_knowledge_base(session, user_external_id, knowledge_base_id) in WRITE_ROLES


def user_can_manage_knowledge_base(session: Session, user_external_id: str, knowledge_base_id: UUID) -> bool:
    if is_admin_user(session, user_external_id):
        return True
    return _user_role_for_knowledge_base(session, user_external_id, knowledge_base_id) in MANAGE_ROLES


def is_admin_user(session: Session, user_external_id: str) -> bool:
    return bool(
        session.scalar(
            select(User.id).where(
                User.external_id == user_external_id,
                User.role == "admin",
                User.is_active.is_(True),
            )
        )
    )


def _user_role_for_knowledge_base(session: Session, user_external_id: str, knowledge_base_id: UUID) -> str | None:
    return session.scalar(
        select(KnowledgeBaseMember.role)
        .join(User, User.id == KnowledgeBaseMember.user_id)
        .where(
            KnowledgeBaseMember.knowledge_base_id == knowledge_base_id,
            User.external_id == user_external_id,
        )
    )


def visible_document_filter(user_external_id: str):
    return (
        select(DocumentPermission.id)
        .join(User, User.id == DocumentPermission.user_id)
        .where(DocumentPermission.document_id == KnowledgeDocument.id)
        .exists()
        .is_(False)
    ) | (
        select(DocumentPermission.id)
        .join(User, User.id == DocumentPermission.user_id)
        .where(
            DocumentPermission.document_id == KnowledgeDocument.id,
            User.external_id == user_external_id,
            DocumentPermission.can_view.is_(True),
        )
        .exists()
    )


def grant_document_view_permission(
    session: Session,
    *,
    document_id: UUID,
    actor_external_id: str,
    grantee_external_id: str,
) -> dict[str, Any]:
    document = session.get(KnowledgeDocument, document_id)
    if document is None:
        raise PermissionError("Document was not found")
    if not user_can_manage_knowledge_base(session, actor_external_id, document.knowledge_base_id):
        raise PermissionError("Current user cannot manage this document")
    try:
        user = ensure_user(session, grantee_external_id)
        permission = session.scalar(
            select(DocumentPermission).where(
                DocumentPermission.document_id == document_id,
                DocumentPermission.user_id == user.id,
            )
        )
        if permission is None:
            permission = DocumentPermission(document_id=document_id, user_id=user.id, can_view=True)
            session.add(permission)
        else:
            permission.can_view = True
        session.commit()
        return {"document_id": str(document_id), "user_id": user.external_id, "can_view": True}
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to grant document permission") from exc


def persist_document(
    session: Session,
    *,
    user_external_id: str = LOCAL_OWNER_ID,
    title: str,
    source: str,
    file_type: str,
    content: str,
    chunks: Iterable[dict[str, Any]],
    knowledge_base_id: UUID | None = None,
) -> dict[str, Any]:
    """Store one parsed document and all of its retrievable chunks atomically."""
    try:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id) if knowledge_base_id else None
        if knowledge_base is None:
            knowledge_base = ensure_local_knowledge_base(session, user_external_id)
        if not user_can_write_knowledge_base(session, user_external_id, knowledge_base.id):
            raise PermissionError("Current user cannot write to this knowledge base")
        document = KnowledgeDocument(
            knowledge_base_id=knowledge_base.id,
            title=title,
            source=source,
            file_type=file_type,
            content=content,
        )
        session.add(document)
        session.flush()

        chunk_list = list(chunks)
        embeddings = embed_texts([str(chunk["text"]) for chunk in chunk_list])
        for chunk_index, (chunk, embedding) in enumerate(zip(chunk_list, embeddings), start=1):
            chunk_text = str(chunk["text"])
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    location=dict(chunk.get("location", {"kind": "document"})),
                    embedding=embedding,
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
        if user_external_id is not None and not is_admin_user(session, user_external_id):
            statement = (
                statement.join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id)
                .join(KnowledgeBaseMember, KnowledgeBaseMember.knowledge_base_id == KnowledgeBase.id)
                .join(User, User.id == KnowledgeBaseMember.user_id)
                .where(User.external_id == user_external_id, visible_document_filter(user_external_id))
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
        if user_external_id is not None and not is_admin_user(session, user_external_id):
            statement = (
                statement.join(KnowledgeBase, KnowledgeBase.id == KnowledgeDocument.knowledge_base_id)
                .join(KnowledgeBaseMember, KnowledgeBaseMember.knowledge_base_id == KnowledgeBase.id)
                .join(User, User.id == KnowledgeBaseMember.user_id)
                .where(User.external_id == user_external_id, visible_document_filter(user_external_id))
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
    results, _ = hybrid_search_chunks_with_diagnostics(session, question, limit, user_external_id)
    return results


def hybrid_search_chunks_with_diagnostics(
    session: Session,
    question: str,
    limit: int = 3,
    user_external_id: str | None = None,
) -> tuple[list[RetrievedChunk], dict[str, object]]:
    """Search with score-stage counts for workflow observability."""
    try:
        documents = load_document_records(session, user_external_id)
        candidate_limit = max(20, limit * 6)
        lexical_hits = HybridRetriever(documents).search(question, limit=candidate_limit)
        semantic_hits = semantic_search_chunks(session, question, limit=candidate_limit, user_external_id=user_external_id)
        fused_hits = merge_search_results(lexical_hits, semantic_hits, candidate_limit)
        reranked_candidates = rerank_candidates(question, fused_hits)
        final_hits = reranked_candidates[:limit]
        return final_hits, {
            "mode": "keyword + pgvector + fusion + reranker",
            "lexical_candidates": len(lexical_hits),
            "semantic_candidates": len(semantic_hits),
            "fused_candidates": len(fused_hits),
            "selected_candidates": len(final_hits),
            "reranker_applied": any(hit.rerank_score is not None for hit in final_hits),
            "candidate_ranking": _candidate_ranking(fused_hits, reranked_candidates, limit),
        }
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL vector search is unavailable") from exc


def semantic_search_chunks(
    session: Session,
    question: str,
    limit: int = 12,
    user_external_id: str | None = None,
) -> list[RetrievedChunk]:
    embedding = vector_literal(embed_query(question))
    membership_join = ""
    membership_filter = ""
    document_acl_filter = ""
    params: dict[str, Any] = {"embedding": embedding, "limit": limit}
    if user_external_id is not None and not is_admin_user(session, user_external_id):
        membership_join = """
            JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
            JOIN knowledge_base_members kbm ON kbm.knowledge_base_id = kb.id
            JOIN users u ON u.id = kbm.user_id
        """
        membership_filter = "AND u.external_id = :user_external_id"
        document_acl_filter = """
            AND (
                NOT EXISTS (
                    SELECT 1 FROM document_permissions dp_all
                    WHERE dp_all.document_id = d.id
                )
                OR EXISTS (
                    SELECT 1 FROM document_permissions dp
                    JOIN users du ON du.id = dp.user_id
                    WHERE dp.document_id = d.id
                    AND du.external_id = :user_external_id
                    AND dp.can_view = true
                )
            )
        """
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
            {document_acl_filter}
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
                lexical_score=round(lexical_score, 4),
                semantic_score=round(semantic_score, 4),
                fusion_score=round(combined_score, 4),
            )
        )
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]


def _candidate_ranking(
    fused_hits: list[RetrievedChunk], reranked_candidates: list[RetrievedChunk], limit: int
) -> list[dict[str, object]]:
    fusion_ranks = {chunk.chunk_id: rank for rank, chunk in enumerate(fused_hits, start=1)}
    return [
        {
            "chunk_id": chunk.chunk_id,
            "title": chunk.title,
            "fusion_rank": fusion_ranks[chunk.chunk_id],
            "final_rank": rank if rank <= limit else None,
            "lexical_score": chunk.lexical_score,
            "semantic_score": chunk.semantic_score,
            "fusion_score": chunk.fusion_score,
            "rerank_score": chunk.rerank_score,
            "decision": "selected" if rank <= limit else "discarded",
            "reason": (
                "Selected in final Top K after reranking"
                if rank <= limit and chunk.rerank_score is not None
                else "Selected by fusion fallback"
                if rank <= limit
                else f"Outside final Top {limit} after reranking"
                if chunk.rerank_score is not None
                else f"Outside final Top {limit} by fusion fallback"
            ),
        }
        for rank, chunk in enumerate(reranked_candidates, start=1)
    ]


def database_is_ready(session: Session) -> bool:
    try:
        session.execute(text("SELECT 1"))
        required_user_columns = {
            "external_id",
            "username",
            "password_hash",
            "display_name",
            "role",
            "tenant_id",
            "department",
            "is_active",
        }
        available_user_columns = set(
            session.scalars(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = 'users'"
                )
            ).all()
        )
        return required_user_columns.issubset(available_user_columns)
    except SQLAlchemyError:
        session.rollback()
        return False


def load_system_diagnostics(session: Session) -> dict[str, Any]:
    """Return database and index health data for the operations panel."""
    try:
        vector_installed = bool(
            session.execute(text("select exists(select 1 from pg_extension where extname = 'vector')")).scalar_one()
        )
        alembic_version = session.execute(text("select version_num from alembic_version")).scalar_one_or_none()

        table_counts = {
            "users": session.scalar(select(func.count()).select_from(User)) or 0,
            "knowledge_bases": session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0,
            "knowledge_base_members": session.scalar(select(func.count()).select_from(KnowledgeBaseMember)) or 0,
            "documents": session.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0,
            "document_chunks": session.scalar(select(func.count()).select_from(DocumentChunk)) or 0,
            "workflow_runs": session.scalar(select(func.count()).select_from(WorkflowRun)) or 0,
            "workflow_trace_steps": session.scalar(select(func.count()).select_from(WorkflowTraceStep)) or 0,
        }

        documents_without_chunks = session.execute(
            select(KnowledgeDocument.id, KnowledgeDocument.title)
            .outerjoin(DocumentChunk)
            .group_by(KnowledgeDocument.id)
            .having(func.count(DocumentChunk.id) == 0)
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(20)
        ).all()
        chunks_missing_embeddings = session.scalar(
            select(func.count()).select_from(DocumentChunk).where(DocumentChunk.embedding.is_(None))
        ) or 0
        duplicate_documents = session.execute(
            text(
                """
                select title, file_type, md5(content) as content_hash, count(*) as duplicate_count
                from documents
                group by knowledge_base_id, title, file_type, md5(content)
                having count(*) > 1
                order by duplicate_count desc, title
                limit 20
                """
            )
        ).mappings().all()
        recent_runs = session.scalars(
            select(WorkflowRun).order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc()).limit(5)
        ).all()

        issues = []
        if table_counts["documents"] and not table_counts["document_chunks"]:
            issues.append("Documents exist but no chunks were indexed")
        if chunks_missing_embeddings:
            issues.append(f"{chunks_missing_embeddings} chunks are missing embeddings")
        if documents_without_chunks:
            issues.append(f"{len(documents_without_chunks)} documents have no chunks")
        if duplicate_documents:
            issues.append(f"{len(duplicate_documents)} possible duplicate document groups found")

        return {
            "database": {
                "connected": True,
                "pgvector_installed": vector_installed,
                "alembic_version": alembic_version,
                "table_counts": table_counts,
            },
            "index": {
                "healthy": not issues,
                "issues": issues,
                "documents_without_chunks": [
                    {"id": str(row.id), "title": row.title} for row in documents_without_chunks
                ],
                "chunks_missing_embeddings": chunks_missing_embeddings,
                "duplicate_documents": [dict(row) for row in duplicate_documents],
            },
            "recent_audit_runs": [
                {
                    "trace_id": run.trace_id,
                    "user_id": run.user_id,
                    "status": run.status,
                    "approval_status": run.approval_status,
                    "duration_ms": run.duration_ms,
                    "question": run.question,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }
                for run in recent_runs
            ],
        }
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to load database diagnostics") from exc


def document_to_record(document: KnowledgeDocument) -> dict[str, Any]:
    knowledge_base = getattr(document, "knowledge_base", None)
    return {
        "id": str(document.id),
        "title": document.title,
        "source": document.source,
        "file_type": document.file_type,
        "content": document.content,
        "owner_id": knowledge_base.owner_id if knowledge_base else LOCAL_OWNER_ID,
        "chunks": [
            {
                "id": str(chunk.id),
                "text": chunk.text,
                "location": chunk.location,
            }
            for chunk in sorted(document.chunks, key=lambda item: item.chunk_index)
        ],
    }


def knowledge_base_to_record(knowledge_base: KnowledgeBase, role: str) -> dict[str, Any]:
    return {
        "id": str(knowledge_base.id),
        "name": knowledge_base.name,
        "owner_id": knowledge_base.owner_id,
        "tenant_id": knowledge_base.tenant_id,
        "department": knowledge_base.department,
        "description": knowledge_base.description,
        "role": role,
        "can_write": role == "admin" or role in WRITE_ROLES,
        "can_manage": role == "admin" or role in MANAGE_ROLES,
        "created_at": knowledge_base.created_at.isoformat() if knowledge_base.created_at else None,
    }


def persist_workflow_run(
    session: Session,
    *,
    trace_id: str,
    user_external_id: str,
    event_type: str,
    question: str,
    status: str,
    duration_ms: int,
    step_count: int,
    summary: str,
    workflow_trace: Iterable[dict[str, Any]],
    approval_status: str = "not_required",
) -> dict[str, Any]:
    try:
        run = WorkflowRun(
            trace_id=trace_id,
            user_id=user_external_id,
            event_type=event_type,
            question=question,
            status=status,
            duration_ms=duration_ms,
            step_count=step_count,
            summary=summary,
            approval_status=approval_status,
        )
        session.add(run)
        session.flush()
        for step_index, step in enumerate(workflow_trace, start=1):
            session.add(
                WorkflowTraceStep(
                    workflow_run_id=run.id,
                    step_index=step_index,
                    name=str(step["name"]),
                    status=str(step["status"]),
                    detail=str(step["detail"]),
                    duration_ms=int(step["duration_ms"]),
                    prompt=str(step["prompt"]),
                    tool_calls=list(step.get("tool_calls", [])),
                    input_tokens=int(step["input_tokens"]),
                    output_tokens=int(step["output_tokens"]),
                    failure_reason=step.get("failure_reason"),
                    trace_data=dict(step.get("trace_data", {})),
                )
            )
        session.commit()
        session.refresh(run)
        return workflow_run_to_record(run)
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its workflow schema has not been migrated") from exc


def load_audit_event_records(session: Session, user_external_id: str | None = None) -> list[dict[str, Any]]:
    try:
        statement = select(WorkflowRun).options(selectinload(WorkflowRun.steps)).order_by(
            WorkflowRun.created_at, WorkflowRun.id
        )
        if user_external_id is not None:
            statement = statement.where(WorkflowRun.user_id == user_external_id)
        runs = session.scalars(statement).all()
        return [workflow_run_to_record(run) for run in runs]
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its workflow schema has not been migrated") from exc


def load_workflow_trace_records(session: Session, trace_id: str) -> dict[str, Any] | None:
    try:
        run = session.scalar(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.steps))
            .where(WorkflowRun.trace_id == trace_id)
        )
        return workflow_run_to_record(run) if run is not None else None
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("PostgreSQL is unavailable or its workflow schema has not been migrated") from exc


def review_workflow_run(
    session: Session,
    *,
    trace_id: str,
    user_external_id: str,
    decision: str,
    comment: str | None,
) -> dict[str, Any]:
    try:
        run = session.scalar(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.steps))
            .where(WorkflowRun.trace_id == trace_id)
        )
        if run is None:
            raise WorkflowReviewError("Audit run was not found")
        if run.user_id != user_external_id:
            raise WorkflowReviewError("You cannot review another user's audit run")
        if run.approval_status != "pending":
            raise WorkflowReviewError("This audit run is not awaiting human review")
        run.approval_status = decision
        run.review_decision = decision
        run.reviewed_by = user_external_id
        run.review_comment = comment
        run.reviewed_at = func.now()
        run.status = "completed" if decision == "approved" else "rejected"
        session.commit()
        session.refresh(run)
        return workflow_run_to_record(run)
    except WorkflowReviewError:
        session.rollback()
        raise
    except SQLAlchemyError as exc:
        session.rollback()
        raise DatabaseUnavailableError("Unable to save workflow review") from exc


def workflow_run_to_record(run: WorkflowRun) -> dict[str, Any]:
    ordered_steps = sorted(run.steps, key=lambda item: item.step_index)
    return {
        "id": str(run.id),
        "event": run.event_type,
        "trace_id": run.trace_id,
        "user_id": run.user_id,
        "question": run.question,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "step_count": run.step_count,
        "summary": run.summary,
        "approval_status": run.approval_status,
        "review_decision": run.review_decision,
        "reviewed_by": run.reviewed_by,
        "review_comment": run.review_comment,
        "reviewed_at": run.reviewed_at.isoformat() if run.reviewed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "workflow_trace": [
            {
                "name": step.name,
                "status": step.status,
                "detail": step.detail,
                "duration_ms": step.duration_ms,
                "prompt": step.prompt,
                "tool_calls": list(step.tool_calls or []),
                "input_tokens": step.input_tokens,
                "output_tokens": step.output_tokens,
                "failure_reason": step.failure_reason,
                "trace_data": step.trace_data,
            }
            for step in ordered_steps
        ],
    }
