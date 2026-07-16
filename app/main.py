from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.chunking import build_chunks
from app.services.auth import AuthError, create_access_token, verify_access_token
from app.services.model_provider import ChatProviderSettings, ModelConfigurationError, ModelProviderSettings
from app.services.object_storage import ObjectStorageError, store_upload
from app.services.parsers import DocumentParseError, EmptyDocumentError, UnsupportedFileTypeError, parse_document_sections
from app.services.report_export import export_report
from app.services.retrieval import HybridRetriever
from app.services.workflow import run_audit_workflow


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = ROOT / "app" / "data" / "sample_documents.json"
RUNTIME_DIR = ROOT / "data" / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
RUNTIME_DOCUMENTS_PATH = RUNTIME_DIR / "documents.json"
# Legacy sample documents retain this internal owner id. It is not a login account.
DEFAULT_USER_ID = "local-demo"
KNOWLEDGE_BASE_HEADER = "X-Knowledge-Base-Id"
class DocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    source: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=20, max_length=20000)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class EvaluationCase(BaseModel):
    question: str
    expected_document_id: str


class ReportExportRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    export_format: str = Field(default="markdown", pattern="^(json|markdown|pdf)$")


class WorkflowReviewRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: Optional[str] = Field(default=None, max_length=500)
    corrected_findings: Optional[list[dict[str, Any]]] = Field(default=None, max_length=50)


class UrlIngestRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    url: str = Field(min_length=8, max_length=1000)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    department: str = Field(default="general", min_length=2, max_length=100)


class KnowledgeBaseMemberRequest(BaseModel):
    user_id: str = Field(min_length=2, max_length=100)
    role: str = Field(pattern="^(owner|editor|viewer)$")


class DocumentPermissionRequest(BaseModel):
    user_id: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=120)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=120)
    display_name: str = Field(min_length=2, max_length=120)
    tenant_id: str = Field(default="tenant-demo", min_length=2, max_length=100)
    department: str = Field(default="general", max_length=100)


class UserCreateRequest(RegisterRequest):
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")
    tenant_id: Optional[str] = Field(default=None, min_length=2, max_length=100)
    department: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


class AuthenticatedUser(BaseModel):
    id: str
    display_name: str
    role: str
    tenant_id: str = "tenant-demo"
    department: str = "general"
    auth_mode: str = "jwt"


def load_seed_documents() -> list[dict[str, Any]]:
    with DOCUMENTS_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def load_documents() -> list[dict[str, Any]]:
    seed_documents = load_seed_documents()
    persisted_documents = load_persisted_documents()
    if persisted_documents is not None:
        return seed_documents + persisted_documents
    if not RUNTIME_DOCUMENTS_PATH.exists():
        return seed_documents
    with RUNTIME_DOCUMENTS_PATH.open(encoding="utf-8") as file:
        runtime_documents = json.load(file)
    return seed_documents + runtime_documents


def load_persisted_documents() -> list[dict[str, Any]] | None:
    if not os.getenv("DATABASE_URL"):
        return None
    try:
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import database_is_ready, load_document_records

        session = get_session_factory()()
    except Exception:
        return None
    try:
        if not database_is_ready(session):
            return None
        return load_document_records(session)
    except RuntimeError:
        return None
    finally:
        session.close()


def load_runtime_documents() -> list[dict[str, Any]]:
    if not RUNTIME_DOCUMENTS_PATH.exists():
        return []
    with RUNTIME_DOCUMENTS_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def save_runtime_document(document: dict[str, Any]) -> None:
    RUNTIME_DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    runtime_documents = load_runtime_documents()
    runtime_documents.append(document)
    with RUNTIME_DOCUMENTS_PATH.open("w", encoding="utf-8") as file:
        json.dump(runtime_documents, file, ensure_ascii=False, indent=2)


def add_document(document: dict[str, Any]) -> None:
    global retriever
    documents.append(document)
    retriever = HybridRetriever(documents)


def document_visible_to_user(document: dict[str, Any], user_external_id: str) -> bool:
    return document.get("owner_id", DEFAULT_USER_ID) == user_external_id


def get_authenticated_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> AuthenticatedUser:
    if not authorization:
        raise HTTPException(status_code=401, detail="Login is required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    try:
        payload = verify_access_token(token.strip())
    except AuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    user_id = str(payload["sub"])
    account = database_account_by_user_id(user_id)
    if account is None:
        raise HTTPException(status_code=401, detail="User is unavailable or has been disabled")
    return AuthenticatedUser(
        id=user_id,
        display_name=str(account["display_name"]),
        role=str(account["role"]),
        tenant_id=str(account["tenant_id"]),
        department=str(account["department"]),
    )


def database_account_by_user_id(user_external_id: str) -> dict[str, Any] | None:
    session = database_session()
    if session is None:
        return None
    try:
        from app.repositories.knowledge_repository import get_user_account

        return get_user_account(session, user_external_id)
    finally:
        session.close()


def require_admin(current_user: AuthenticatedUser) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges are required")


def database_session():
    if not os.getenv("DATABASE_URL"):
        return None
    try:
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import database_is_ready

        session = get_session_factory()()
        if database_is_ready(session):
            return session
        session.close()
    except Exception:
        return None
    return None


def parse_uuid_or_400(value: str, name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {name}") from exc


def selected_knowledge_base_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def user_documents(user_external_id: str) -> list[dict[str, Any]]:
    return [document for document in documents if document_visible_to_user(document, user_external_id)]


def document_summary(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document["id"],
        "title": document["title"],
        "source": document["source"],
        "chunk_count": len(document.get("chunks", [])) or 1,
    }


def seed_document_summaries(user_external_id: str) -> list[dict[str, Any]]:
    return [document_summary(document) for document in load_seed_documents() if document_visible_to_user(document, user_external_id)]


def load_persisted_document_summaries(user_external_id: str) -> list[dict[str, Any]] | None:
    if not os.getenv("DATABASE_URL"):
        return None
    try:
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import database_is_ready, list_document_summaries

        session = get_session_factory()()
    except Exception:
        return None
    try:
        if not database_is_ready(session):
            return None
        return list_document_summaries(session, user_external_id)
    except RuntimeError:
        return None
    finally:
        session.close()


def load_persisted_audit_log(user_external_id: str) -> list[dict[str, Any]] | None:
    if not os.getenv("DATABASE_URL"):
        return None
    try:
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import database_is_ready, load_audit_event_records

        session = get_session_factory()()
    except Exception:
        return None
    try:
        if not database_is_ready(session):
            return None
        return load_audit_event_records(session, user_external_id)
    except RuntimeError:
        return None
    finally:
        session.close()


def persist_or_save_runtime(document: dict[str, Any], user_external_id: str) -> dict[str, Any]:
    """Prefer PostgreSQL; keep a JSON fallback for direct local development."""
    document["owner_id"] = user_external_id
    knowledge_base_id = selected_knowledge_base_uuid(document.get("knowledge_base_id"))
    # 数据库是生产环境的权威数据源；连接或迁移未就绪时才降级到本地 JSON，保证开发环境仍可运行。
    if os.getenv("DATABASE_URL"):
        try:
            from app.db import get_session_factory
            from app.repositories.knowledge_repository import (
                DatabaseUnavailableError,
                database_is_ready,
                persist_document,
            )

            session = get_session_factory()()
        except Exception:
            session = None
        try:
            if session is not None and database_is_ready(session):
                try:
                    persisted_document = persist_document(
                        session,
                        user_external_id=user_external_id,
                        title=document["title"],
                        source=document["source"],
                        file_type=document["file_type"],
                        content=document["content"],
                        chunks=document["chunks"],
                        knowledge_base_id=knowledge_base_id,
                    )
                    return persisted_document
                except PermissionError as error:
                    raise HTTPException(status_code=403, detail=str(error)) from error
                except DatabaseUnavailableError:
                    pass
        finally:
            if session is not None:
                session.close()

    save_runtime_document(document)
    return document


def search_user_evidence(question: str, user_external_id: str):
    return search_user_evidence_with_diagnostics(question, user_external_id)[0]


def search_user_evidence_with_diagnostics(question: str, user_external_id: str):
    # 优先走数据库权限过滤后的混合检索，避免先检索再过滤造成越权证据进入工作流。
    if os.getenv("DATABASE_URL"):
        try:
            from app.db import get_session_factory
            from app.repositories.knowledge_repository import (
                DatabaseUnavailableError,
                database_is_ready,
                hybrid_search_chunks_with_diagnostics,
            )

            session = get_session_factory()()
        except Exception:
            session = None
        try:
            if session is not None and database_is_ready(session):
                try:
                    persisted_hits, diagnostics = hybrid_search_chunks_with_diagnostics(
                        session, question, user_external_id=user_external_id
                    )
                    if persisted_hits:
                        return persisted_hits, diagnostics
                except DatabaseUnavailableError:
                    pass
        finally:
            if session is not None:
                session.close()
    # 本地模式只检索当前用户可见文档，同时返回统一的诊断结构供 Trace 页面展示。
    hits = HybridRetriever(user_documents(user_external_id)).search(question)
    return hits, {
        "mode": "local lexical fallback",
        "lexical_candidates": len(hits),
        "semantic_candidates": 0,
        "fused_candidates": len(hits),
        "selected_candidates": len(hits),
        "reranker_applied": False,
    }


def persist_audit_event(
    *,
    event_type: str,
    user_external_id: str,
    question: str,
    response: dict[str, object],
) -> None:
    trace_duration_ms = sum(step["duration_ms"] for step in response["workflow_trace"])
    if os.getenv("DATABASE_URL"):
        try:
            from app.db import get_session_factory
            from app.repositories.knowledge_repository import (
                DatabaseUnavailableError,
                database_is_ready,
                persist_workflow_run,
            )

            session = get_session_factory()()
        except Exception:
            session = None
        try:
            if session is not None and database_is_ready(session):
                try:
                    summary = response["answer"] if event_type == "question_answered" else response["report"]["summary"]
                    persist_workflow_run(
                        session,
                        trace_id=str(response["trace_id"]),
                        user_external_id=user_external_id,
                        event_type=event_type,
                        question=question,
                        status="pending_review" if response.get("approval_status") == "pending" else "completed",
                        duration_ms=trace_duration_ms,
                        step_count=len(response["workflow_trace"]),
                        summary=str(summary),
                        workflow_trace=list(response["workflow_trace"]),
                        approval_status=str(response.get("approval_status", "not_required")),
                    )
                    return
                except DatabaseUnavailableError:
                    pass
        finally:
            if session is not None:
                session.close()

    event_payload = {
        "event": event_type,
        "trace_id": response["trace_id"],
        "question": question,
        "user_id": user_external_id,
        "duration_ms": trace_duration_ms,
        "step_count": len(response["workflow_trace"]),
        "workflow_trace": response["workflow_trace"],
        "approval_status": response.get("approval_status", "not_required"),
    }
    if event_type == "question_answered":
        event_payload.update(
            {
                "evidence_ids": [item["document_id"] for item in response["citations"]],
                "risk_levels": [item["level"] for item in response["findings"]],
                "summary": response["answer"],
            }
        )
    else:
        event_payload.update({"summary": response["report"]["summary"]})
    audit_log.append(event_payload)


documents = load_documents()
retriever = HybridRetriever(documents)
audit_log: list[dict[str, object]] = []

app = FastAPI(title="Enterprise Knowledge Audit Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(ROOT / "web" / "favicon.ico")


@app.get("/api/health")
def health() -> dict[str, object]:
    try:
        model_status = ModelProviderSettings.from_environment().public_status()
    except ModelConfigurationError as error:
        model_status = {"provider": "invalid", "remote_enabled": False, "configuration_error": str(error)}
    try:
        chat_status = ChatProviderSettings.from_environment().public_status()
    except ModelConfigurationError as error:
        chat_status = {"provider": "invalid", "remote_enabled": False, "configuration_error": str(error)}
    return {"status": "ok", "document_count": len(documents), "model": model_status, "chat": chat_status}


@app.get("/api/model-config")
def get_model_config() -> dict[str, object]:
    """Expose active model mode without ever returning the API key."""
    try:
        return {
            "embedding": ModelProviderSettings.from_environment().public_status(),
            "chat": ChatProviderSettings.from_environment().public_status(),
        }
    except ModelConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/admin/system-status")
def get_system_status(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> dict[str, object]:
    require_admin(current_user)
    try:
        model_status = ModelProviderSettings.from_environment().public_status()
    except ModelConfigurationError as error:
        model_status = {"provider": "invalid", "remote_enabled": False, "configuration_error": str(error)}
    try:
        chat_status = ChatProviderSettings.from_environment().public_status()
    except ModelConfigurationError as error:
        chat_status = {"provider": "invalid", "remote_enabled": False, "configuration_error": str(error)}

    payload: dict[str, object] = {
        "status": "ok",
        "user": {"id": current_user.id, "role": current_user.role},
        "models": {"embedding": model_status, "chat": chat_status},
    }
    if not os.getenv("DATABASE_URL"):
        payload.update(
            {
                "database": {
                    "connected": False,
                    "pgvector_installed": False,
                    "alembic_version": None,
                    "table_counts": {
                        "documents": len(documents),
                        "document_chunks": sum(len(document.get("chunks", [])) for document in documents),
                        "workflow_runs": len(audit_log),
                        "workflow_trace_steps": sum(len(event.get("workflow_trace", [])) for event in audit_log),
                    },
                },
                "index": {
                    "healthy": True,
                    "issues": ["PostgreSQL is not configured; using in-memory/json fallback"],
                    "documents_without_chunks": [],
                    "chunks_missing_embeddings": 0,
                    "duplicate_documents": [],
                },
                "recent_audit_runs": audit_log[-5:],
            }
        )
        return payload

    try:
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import DatabaseUnavailableError, load_system_diagnostics

        session = get_session_factory()()
    except Exception as error:
        raise HTTPException(status_code=503, detail="System diagnostics are unavailable") from error
    try:
        payload.update(load_system_diagnostics(session))
        return payload
    except DatabaseUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        session.close()


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict[str, object]:
    account = None
    session = database_session()
    if session is not None:
        try:
            from app.repositories.knowledge_repository import authenticate_database_user

            account = authenticate_database_user(session, payload.username, payload.password)
        finally:
            session.close()
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(account)
    user_payload = {
        "id": account["user_id"],
        "display_name": account["display_name"],
        "role": account["role"],
        "tenant_id": account["tenant_id"],
        "department": account["department"],
    }
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 8 * 60 * 60,
        "user": user_payload,
    }


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest) -> dict[str, object]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Registration requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import create_user_record

        user = create_user_record(
            session,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role="user",
            tenant_id=payload.tenant_id,
            department=payload.department.strip() or "general",
        )
        return user
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    finally:
        session.close()


@app.get("/api/me")
def get_current_user(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> dict[str, str]:
    return {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id,
        "department": current_user.department,
        "auth_mode": current_user.auth_mode,
    }


@app.get("/api/users")
def list_users(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> list[dict[str, object]]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="User directory requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import list_user_records

        return list_user_records(session)
    finally:
        session.close()


@app.post("/api/admin/users", status_code=201)
def create_user(payload: UserCreateRequest, current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> dict[str, object]:
    require_admin(current_user)
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="User management requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import create_user_record

        return create_user_record(
            session,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
            tenant_id=payload.tenant_id,
            department=payload.department.strip() or "general",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    finally:
        session.close()


@app.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, object]:
    require_admin(current_user)
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="User management requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import update_user_record

        return update_user_record(session, external_id=user_id, **payload.model_dump(exclude_unset=True))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    finally:
        session.close()


@app.get("/api/knowledge-bases")
def list_knowledge_bases(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> list[dict[str, object]]:
    session = database_session()
    if session is not None:
        try:
            from app.repositories.knowledge_repository import list_knowledge_base_records

            # A registered user may not belong to a knowledge base yet. Do not
            # fall through to the demo mapping, which only accepts demo ids.
            return list_knowledge_base_records(session, current_user.id)
        finally:
            session.close()
    raise HTTPException(status_code=503, detail="Knowledge base management requires PostgreSQL")


@app.post("/api/knowledge-bases", status_code=201)
def create_kb(
    payload: KnowledgeBaseCreateRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, object]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Knowledge base management requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import create_knowledge_base

        return create_knowledge_base(
            session,
            name=payload.name,
            owner_external_id=current_user.id,
            tenant_id=current_user.tenant_id,
            department=payload.department,
            description=payload.description,
        )
    finally:
        session.close()


@app.get("/api/knowledge-bases/{knowledge_base_id}/members")
def get_kb_members(
    knowledge_base_id: str,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> list[dict[str, object]]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Knowledge base member management requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import list_knowledge_base_members

        return list_knowledge_base_members(session, parse_uuid_or_400(knowledge_base_id, "knowledge_base_id"), current_user.id)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    finally:
        session.close()


@app.put("/api/knowledge-bases/{knowledge_base_id}/members")
def put_kb_member(
    knowledge_base_id: str,
    payload: KnowledgeBaseMemberRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, object]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Knowledge base member management requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import upsert_knowledge_base_member

        return upsert_knowledge_base_member(
            session,
            knowledge_base_id=parse_uuid_or_400(knowledge_base_id, "knowledge_base_id"),
            actor_external_id=current_user.id,
            member_external_id=payload.user_id,
            role=payload.role,
        )
    except (PermissionError, ValueError) as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    finally:
        session.close()


@app.delete("/api/knowledge-bases/{knowledge_base_id}/members/{member_user_id}", status_code=204)
def delete_kb_member(
    knowledge_base_id: str,
    member_user_id: str,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Response:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Knowledge base member management requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import remove_knowledge_base_member

        remove_knowledge_base_member(
            session,
            knowledge_base_id=parse_uuid_or_400(knowledge_base_id, "knowledge_base_id"),
            actor_external_id=current_user.id,
            member_external_id=member_user_id,
        )
        return Response(status_code=204)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    finally:
        session.close()


@app.get("/api/documents")
def list_documents(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> list[dict[str, Any]]:
    persisted_summaries = load_persisted_document_summaries(current_user.id)
    if persisted_summaries is not None:
        return seed_document_summaries(current_user.id) + persisted_summaries
    return [document_summary(item) for item in user_documents(current_user.id)]


@app.post("/api/documents/{document_id}/reindex")
def reindex_document(document_id: str, current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> dict[str, Any]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Index repair requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import run_index_task
        task = run_index_task(session, document_id=parse_uuid_or_400(document_id, "document_id"), task_type="rebuild", requested_by=current_user.id)
        if task["status"] == "failed":
            raise HTTPException(status_code=500, detail=task["error"])
        return task
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    finally:
        session.close()


@app.post("/api/admin/index/backfill")
def backfill_embeddings(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> dict[str, Any]:
    require_admin(current_user)
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Index repair requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import run_index_task
        return run_index_task(session, document_id=None, task_type="backfill_embeddings", requested_by=current_user.id)
    finally:
        session.close()


@app.get("/api/admin/index/tasks")
def index_tasks(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> list[dict[str, Any]]:
    require_admin(current_user)
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Index task history requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import list_index_tasks
        return list_index_tasks(session)
    finally:
        session.close()


@app.delete("/api/documents/{document_id}", status_code=204)
def remove_document(document_id: str, current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> Response:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Document deletion requires PostgreSQL")
    try:
        from app.repositories.knowledge_repository import delete_document
        delete_document(session, document_id=parse_uuid_or_400(document_id, "document_id"), actor_external_id=current_user.id)
        return Response(status_code=204)
    except (PermissionError, ValueError) as error:
        raise HTTPException(status_code=403 if isinstance(error, PermissionError) else 404, detail=str(error)) from error
    finally:
        session.close()


@app.post("/api/documents", status_code=201)
def create_document(
    payload: DocumentCreate,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    knowledge_base_id: Optional[str] = Header(default=None, alias=KNOWLEDGE_BASE_HEADER),
) -> dict[str, str]:
    document_id = str(uuid4())
    document = {
        "id": document_id,
        **payload.model_dump(),
        "file_type": "text",
        "chunks": build_chunks(
            document_id,
            [{"text": payload.content, "location": {"kind": "document"}}],
        ),
    }
    selected_kb_id = selected_knowledge_base_uuid(knowledge_base_id)
    if selected_kb_id:
        document["knowledge_base_id"] = str(selected_kb_id)
    document = persist_or_save_runtime(document, current_user.id)
    add_document(document)
    audit_log.append({"event": "document_ingested", "document_id": document["id"], "user_id": current_user.id})
    return {"id": document["id"], "message": "Document indexed"}


@app.post("/api/documents/upload", status_code=201)
async def upload_document(
    title: str = Form(..., min_length=2, max_length=120),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    knowledge_base_id: Optional[str] = Header(default=None, alias=KNOWLEDGE_BASE_HEADER),
) -> dict[str, str]:
    raw_content = await file.read()
    filename = Path(file.filename or "uploaded.txt").name
    if os.getenv("REDIS_URL"):
        document_id = str(uuid4())
        temp_dir = RUNTIME_DIR / "pending"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{document_id}.upload"
        temp_path.write_bytes(raw_content)
        try:
            from app.services.tasks import enqueue_task
            task = enqueue_task(
                task_type="upload", requested_by=current_user.id,
                # The document is created by the worker; setting this FK before
                # then makes PostgreSQL reject the queued task.
                document_id=None,
                payload={"handler": "upload", "temp_path": str(temp_path), "filename": filename,
                         "content_type": file.content_type or "application/octet-stream", "title": title,
                         "document_id": document_id, "requested_by": current_user.id,
                         "knowledge_base_id": knowledge_base_id},
            )
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=503, detail=f"Task queue is unavailable: {exc}") from exc
        return JSONResponse(status_code=202, content={"id": document_id, "task_id": task["id"], "status": "queued", "message": "Upload accepted"})
    try:
        parsed_document = parse_document_sections(filename, raw_content)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = str(uuid4())
    try:
        stored_object = store_upload(
            content=raw_content,
            filename=filename,
            object_id=document_id,
            content_type=file.content_type or "application/octet-stream",
            fallback_dir=UPLOAD_DIR,
        )
    except ObjectStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    document = {
        "id": document_id,
        "title": title,
        "source": stored_object.source,
        "file_type": parsed_document.file_type,
        "content": parsed_document.text,
        "chunks": build_chunks(
            document_id,
            [{"text": section.text, "location": section.location} for section in parsed_document.sections],
        ),
    }
    selected_kb_id = selected_knowledge_base_uuid(knowledge_base_id)
    if selected_kb_id:
        document["knowledge_base_id"] = str(selected_kb_id)
    document = persist_or_save_runtime(document, current_user.id)
    add_document(document)
    audit_log.append(
        {
            "event": "document_uploaded",
            "document_id": document["id"],
            "source": document["source"],
            "storage_backend": stored_object.backend,
            "user_id": current_user.id,
        }
    )
    return {
        "id": document["id"],
        "message": "Document uploaded and indexed",
        "source": document["source"],
        "storage_backend": stored_object.backend,
    }


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> dict[str, Any]:
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Task status requires PostgreSQL")
    try:
        from app.services.tasks import task_record
        task = task_record(task_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Task was not found")
    if task["requested_by"] != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="You cannot view this task")
    return task


@app.post("/api/documents/ingest-url", status_code=201)
def ingest_url_document(
    payload: UrlIngestRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    knowledge_base_id: Optional[str] = Header(default=None, alias=KNOWLEDGE_BASE_HEADER),
) -> dict[str, str]:
    parsed_url = urlparse(payload.url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise HTTPException(status_code=400, detail="Only http and https URLs can be ingested")

    try:
        response = httpx.get(payload.url, follow_redirects=True, timeout=15.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Unable to fetch URL: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and not payload.url.lower().endswith((".html", ".htm")):
        raise HTTPException(status_code=415, detail="URL ingestion currently supports HTML pages only")
    if len(response.content) > 2_000_000:
        raise HTTPException(status_code=413, detail="HTML page is too large to ingest")

    try:
        parsed_document = parse_document_sections("webpage.html", response.content)
    except EmptyDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = str(uuid4())
    document = {
        "id": document_id,
        "title": payload.title,
        "source": str(response.url),
        "file_type": parsed_document.file_type,
        "content": parsed_document.text,
        "chunks": build_chunks(
            document_id,
            [{"text": section.text, "location": section.location} for section in parsed_document.sections],
        ),
    }
    selected_kb_id = selected_knowledge_base_uuid(knowledge_base_id)
    if selected_kb_id:
        document["knowledge_base_id"] = str(selected_kb_id)
    document = persist_or_save_runtime(document, current_user.id)
    add_document(document)
    audit_log.append(
        {
            "event": "url_ingested",
            "document_id": document["id"],
            "source": document["source"],
            "user_id": current_user.id,
        }
    )
    return {"id": document["id"], "message": "URL ingested and indexed", "source": document["source"]}


@app.put("/api/documents/{document_id}/permissions")
def grant_document_permission(
    document_id: str,
    payload: DocumentPermissionRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, object]:
    session = database_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Document permissions require PostgreSQL")
    try:
        from app.repositories.knowledge_repository import grant_document_view_permission

        return grant_document_view_permission(
            session,
            document_id=parse_uuid_or_400(document_id, "document_id"),
            actor_external_id=current_user.id,
            grantee_external_id=payload.user_id,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    finally:
        session.close()


@app.post("/api/ask")
def ask(
    payload: QuestionRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, object]:
    response = run_audit_workflow(
        payload.question, lambda question: search_user_evidence_with_diagnostics(question, current_user.id)
    )
    if not response["citations"]:
        raise HTTPException(status_code=404, detail="No searchable evidence")
    persist_audit_event(event_type="question_answered", user_external_id=current_user.id, question=payload.question, response=response)
    return response


@app.get("/api/audit-log")
def get_audit_log(current_user: AuthenticatedUser = Depends(get_authenticated_user)) -> list[dict[str, object]]:
    persisted_audit_log = load_persisted_audit_log(None if current_user.role == "admin" else current_user.id)
    if persisted_audit_log is not None:
        return persisted_audit_log
    visible_events = audit_log if current_user.role == "admin" else [
        event for event in audit_log if event.get("user_id", DEFAULT_USER_ID) == current_user.id
    ]
    return visible_events[-50:]


@app.post("/api/audit-runs/{trace_id}/review")
def review_audit_run(
    trace_id: str,
    payload: WorkflowReviewRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, Any]:
    if current_user.role not in {"admin", "user"}:
        raise HTTPException(status_code=403, detail="Current role cannot review audit runs")
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Workflow reviews require PostgreSQL")
    try:
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import (
            DatabaseUnavailableError,
            WorkflowReviewError,
            review_workflow_run,
        )

        session = get_session_factory()()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Workflow review storage is unavailable") from error
    try:
        return review_workflow_run(
            session,
            trace_id=trace_id,
            user_external_id=current_user.id,
            decision=payload.decision,
            comment=payload.comment,
            corrected_findings=payload.corrected_findings,
        )
    except WorkflowReviewError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except DatabaseUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        session.close()


@app.get("/api/evaluation-results")
def get_evaluation_results() -> dict[str, object]:
    results_path = ROOT / "data" / "evaluation_results.json"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="Evaluation results have not been generated")
    with results_path.open(encoding="utf-8") as file:
        return json.load(file)


@app.post("/api/evaluate")
def evaluate(
    cases: list[EvaluationCase],
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> dict[str, object]:
    if not cases:
        raise HTTPException(status_code=400, detail="At least one evaluation case is required")
    if os.getenv("REDIS_URL"):
        try:
            from app.services.tasks import enqueue_task
            task = enqueue_task(task_type="evaluation", requested_by=current_user.id,
                                payload={"handler": "evaluation", "requested_by": current_user.id,
                                         "cases": [case.model_dump() for case in cases]})
            return JSONResponse(status_code=202, content={"task_id": task["id"], "status": "queued"})
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Task queue is unavailable: {exc}") from exc
    outcomes = []
    for case in cases:
        result = HybridRetriever(user_documents(current_user.id)).search(case.question, limit=1)
        actual = result[0].document_id if result else None
        outcomes.append(
            {
                "question": case.question,
                "expected_document_id": case.expected_document_id,
                "actual_document_id": actual,
                "passed": actual == case.expected_document_id,
            }
        )
    passed = sum(1 for item in outcomes if item["passed"])
    return {"total": len(outcomes), "passed": passed, "recall_at_1": round(passed / len(outcomes), 3), "outcomes": outcomes}


@app.post("/api/reports/export")
def export_audit_report(
    payload: ReportExportRequest,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
) -> Response:
    response = run_audit_workflow(
        payload.question, lambda question: search_user_evidence_with_diagnostics(question, current_user.id)
    )
    if not response["citations"]:
        raise HTTPException(status_code=404, detail="No searchable evidence")
    persist_audit_event(event_type="report_exported", user_external_id=current_user.id, question=payload.question, response=response)

    try:
        file_bytes, media_type, filename = export_report(response["report"], payload.export_format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
