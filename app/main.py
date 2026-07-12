from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.chunking import build_chunks
from app.services.parsers import DocumentParseError, EmptyDocumentError, UnsupportedFileTypeError, parse_document_sections
from app.services.report_export import export_report
from app.services.retrieval import HybridRetriever
from app.services.workflow import run_audit_workflow


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = ROOT / "app" / "data" / "sample_documents.json"
RUNTIME_DIR = ROOT / "data" / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
RUNTIME_DOCUMENTS_PATH = RUNTIME_DIR / "documents.json"
DEFAULT_USER_ID = "local-demo"
USER_HEADER = "X-User-Id"
DEMO_USERS = {
    "local-demo": "Local Demo",
    "demo-alice": "Alice",
    "demo-bob": "Bob",
}


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


def normalize_user_id(user_external_id: str | None) -> str:
    return (user_external_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID


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
                    )
                    return persisted_document
                except DatabaseUnavailableError:
                    pass
        finally:
            if session is not None:
                session.close()

    save_runtime_document(document)
    return document


def search_user_evidence(question: str, user_external_id: str):
    if os.getenv("DATABASE_URL"):
        try:
            from app.db import get_session_factory
            from app.repositories.knowledge_repository import DatabaseUnavailableError, database_is_ready, hybrid_search_chunks

            session = get_session_factory()()
        except Exception:
            session = None
        try:
            if session is not None and database_is_ready(session):
                try:
                    persisted_hits = hybrid_search_chunks(session, question, user_external_id=user_external_id)
                    if persisted_hits:
                        return persisted_hits
                except DatabaseUnavailableError:
                    pass
        finally:
            if session is not None:
                session.close()
    return HybridRetriever(user_documents(user_external_id)).search(question)


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
                        status="completed",
                        duration_ms=trace_duration_ms,
                        step_count=len(response["workflow_trace"]),
                        summary=str(summary),
                        workflow_trace=list(response["workflow_trace"]),
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
    return {"status": "ok", "document_count": len(documents), "llm_enabled": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/me")
def get_current_user(user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER)) -> dict[str, str]:
    user_external_id = normalize_user_id(user_external_id)
    return {"id": user_external_id, "display_name": DEMO_USERS.get(user_external_id, user_external_id)}


@app.get("/api/documents")
def list_documents(user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER)) -> list[dict[str, Any]]:
    user_external_id = normalize_user_id(user_external_id)
    persisted_summaries = load_persisted_document_summaries(user_external_id)
    if persisted_summaries is not None:
        return seed_document_summaries(user_external_id) + persisted_summaries
    return [document_summary(item) for item in user_documents(user_external_id)]


@app.post("/api/documents", status_code=201)
def create_document(
    payload: DocumentCreate,
    user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER),
) -> dict[str, str]:
    user_external_id = normalize_user_id(user_external_id)
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
    document = persist_or_save_runtime(document, user_external_id)
    add_document(document)
    audit_log.append({"event": "document_ingested", "document_id": document["id"], "user_id": user_external_id})
    return {"id": document["id"], "message": "Document indexed"}


@app.post("/api/documents/upload", status_code=201)
async def upload_document(
    title: str = Form(..., min_length=2, max_length=120),
    file: UploadFile = File(...),
    user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER),
) -> dict[str, str]:
    user_external_id = normalize_user_id(user_external_id)
    raw_content = await file.read()
    filename = Path(file.filename or "uploaded.txt").name
    try:
        parsed_document = parse_document_sections(filename, raw_content)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = str(uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{document_id}_{filename}"
    stored_path = UPLOAD_DIR / stored_name
    stored_path.write_bytes(raw_content)

    document = {
        "id": document_id,
        "title": title,
        "source": f"data/runtime/uploads/{stored_name}",
        "file_type": parsed_document.file_type,
        "content": parsed_document.text,
        "chunks": build_chunks(
            document_id,
            [{"text": section.text, "location": section.location} for section in parsed_document.sections],
        ),
    }
    document = persist_or_save_runtime(document, user_external_id)
    add_document(document)
    audit_log.append(
        {
            "event": "document_uploaded",
            "document_id": document["id"],
            "source": document["source"],
            "user_id": user_external_id,
        }
    )
    return {"id": document["id"], "message": "Document uploaded and indexed"}


@app.post("/api/ask")
def ask(
    payload: QuestionRequest,
    user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER),
) -> dict[str, object]:
    user_external_id = normalize_user_id(user_external_id)
    response = run_audit_workflow(payload.question, lambda question: search_user_evidence(question, user_external_id))
    if not response["citations"]:
        raise HTTPException(status_code=404, detail="No searchable evidence")
    persist_audit_event(event_type="question_answered", user_external_id=user_external_id, question=payload.question, response=response)
    return response


@app.get("/api/audit-log")
def get_audit_log(user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER)) -> list[dict[str, object]]:
    user_external_id = normalize_user_id(user_external_id)
    persisted_audit_log = load_persisted_audit_log(user_external_id)
    if persisted_audit_log is not None:
        return persisted_audit_log
    visible_events = [event for event in audit_log if event.get("user_id", DEFAULT_USER_ID) == user_external_id]
    return visible_events[-50:]


@app.post("/api/evaluate")
def evaluate(
    cases: list[EvaluationCase],
    user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER),
) -> dict[str, object]:
    user_external_id = normalize_user_id(user_external_id)
    if not cases:
        raise HTTPException(status_code=400, detail="At least one evaluation case is required")
    outcomes = []
    for case in cases:
        result = HybridRetriever(user_documents(user_external_id)).search(case.question, limit=1)
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
    user_external_id: str = Header(default=DEFAULT_USER_ID, alias=USER_HEADER),
) -> Response:
    user_external_id = normalize_user_id(user_external_id)
    response = run_audit_workflow(payload.question, lambda question: search_user_evidence(question, user_external_id))
    if not response["citations"]:
        raise HTTPException(status_code=404, detail="No searchable evidence")
    persist_audit_event(event_type="report_exported", user_external_id=user_external_id, question=payload.question, response=response)

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
