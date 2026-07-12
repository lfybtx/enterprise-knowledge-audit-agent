from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.chunking import build_chunks
from app.services.parsers import DocumentParseError, EmptyDocumentError, UnsupportedFileTypeError, parse_document_sections
from app.services.retrieval import HybridRetriever, grounded_answer
from app.services.workflow import run_audit_workflow


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = ROOT / "app" / "data" / "sample_documents.json"
RUNTIME_DIR = ROOT / "data" / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
RUNTIME_DOCUMENTS_PATH = RUNTIME_DIR / "documents.json"


class DocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    source: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=20, max_length=20000)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class EvaluationCase(BaseModel):
    question: str
    expected_document_id: str


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
    from app.db import get_session_factory
    from app.repositories.knowledge_repository import database_is_ready, load_document_records

    session = get_session_factory()()
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


def persist_or_save_runtime(document: dict[str, Any]) -> dict[str, Any]:
    """Prefer PostgreSQL; keep a JSON fallback for direct local development."""
    if os.getenv("DATABASE_URL"):
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import (
            DatabaseUnavailableError,
            database_is_ready,
            persist_document,
        )

        session = get_session_factory()()
        try:
            if database_is_ready(session):
                try:
                    persisted_document = persist_document(
                        session,
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
            session.close()

    save_runtime_document(document)
    return document


def search_evidence(question: str):
    if os.getenv("DATABASE_URL"):
        from app.db import get_session_factory
        from app.repositories.knowledge_repository import DatabaseUnavailableError, database_is_ready, hybrid_search_chunks

        session = get_session_factory()()
        try:
            if database_is_ready(session):
                try:
                    persisted_hits = hybrid_search_chunks(session, question)
                    if persisted_hits:
                        return persisted_hits
                except DatabaseUnavailableError:
                    pass
        finally:
            session.close()
    return retriever.search(question)


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


@app.get("/api/documents")
def list_documents() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "source": item["source"],
            "chunk_count": len(item.get("chunks", [])) or 1,
        }
        for item in documents
    ]


@app.post("/api/documents", status_code=201)
def create_document(payload: DocumentCreate) -> dict[str, str]:
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
    document = persist_or_save_runtime(document)
    add_document(document)
    audit_log.append({"event": "document_ingested", "document_id": document["id"]})
    return {"id": document["id"], "message": "Document indexed"}


@app.post("/api/documents/upload", status_code=201)
async def upload_document(
    title: str = Form(..., min_length=2, max_length=120),
    file: UploadFile = File(...),
) -> dict[str, str]:
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
    document = persist_or_save_runtime(document)
    add_document(document)
    audit_log.append({"event": "document_uploaded", "document_id": document_id, "source": document["source"]})
    return {"id": document_id, "message": "Document uploaded and indexed"}


@app.post("/api/ask")
def ask(payload: QuestionRequest) -> dict[str, object]:
    response = run_audit_workflow(payload.question, search_evidence)
    if not response["citations"]:
        raise HTTPException(status_code=404, detail="No searchable evidence")
    audit_log.append(
        {
            "event": "question_answered",
            "question": payload.question,
            "evidence_ids": [item["document_id"] for item in response["citations"]],
            "risk_levels": [item["level"] for item in response["findings"]],
        }
    )
    return response


@app.get("/api/audit-log")
def get_audit_log() -> list[dict[str, object]]:
    return audit_log[-50:]


@app.post("/api/evaluate")
def evaluate(cases: list[EvaluationCase]) -> dict[str, object]:
    if not cases:
        raise HTTPException(status_code=400, detail="At least one evaluation case is required")
    outcomes = []
    for case in cases:
        result = retriever.search(case.question, limit=1)
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
