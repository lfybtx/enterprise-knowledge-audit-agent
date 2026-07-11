from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.audit import assess
from app.services.parsers import DocumentParseError, EmptyDocumentError, UnsupportedFileTypeError, parse_document
from app.services.retrieval import HybridRetriever, grounded_answer


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


def load_documents() -> list[dict[str, str]]:
    with DOCUMENTS_PATH.open(encoding="utf-8") as file:
        seed_documents = json.load(file)
    if not RUNTIME_DOCUMENTS_PATH.exists():
        return seed_documents
    with RUNTIME_DOCUMENTS_PATH.open(encoding="utf-8") as file:
        runtime_documents = json.load(file)
    return seed_documents + runtime_documents


def load_runtime_documents() -> list[dict[str, str]]:
    if not RUNTIME_DOCUMENTS_PATH.exists():
        return []
    with RUNTIME_DOCUMENTS_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def save_runtime_document(document: dict[str, str]) -> None:
    RUNTIME_DOCUMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    runtime_documents = load_runtime_documents()
    runtime_documents.append(document)
    with RUNTIME_DOCUMENTS_PATH.open("w", encoding="utf-8") as file:
        json.dump(runtime_documents, file, ensure_ascii=False, indent=2)


def add_document(document: dict[str, str]) -> None:
    global retriever
    documents.append(document)
    retriever = HybridRetriever(documents)


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
def list_documents() -> list[dict[str, str]]:
    return [{"id": item["id"], "title": item["title"], "source": item["source"]} for item in documents]


@app.post("/api/documents", status_code=201)
def create_document(payload: DocumentCreate) -> dict[str, str]:
    document = {"id": str(uuid4()), **payload.model_dump()}
    add_document(document)
    save_runtime_document(document)
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
        file_type, parsed_text = parse_document(filename, raw_content)
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
        "file_type": file_type,
        "content": parsed_text,
    }
    add_document(document)
    save_runtime_document(document)
    audit_log.append({"event": "document_uploaded", "document_id": document_id, "source": document["source"]})
    return {"id": document_id, "message": "Document uploaded and indexed"}


@app.post("/api/ask")
def ask(payload: QuestionRequest) -> dict[str, object]:
    evidence = retriever.search(payload.question)
    if not evidence:
        raise HTTPException(status_code=404, detail="No searchable evidence")

    findings = assess(payload.question, evidence)
    audit_log.append(
        {
            "event": "question_answered",
            "question": payload.question,
            "evidence_ids": [item.document_id for item in evidence],
            "risk_levels": [item.level for item in findings],
        }
    )
    return {
        "answer": grounded_answer(payload.question, evidence),
        "citations": [
            {
                "document_id": item.document_id,
                "title": item.title,
                "source": item.source,
                "excerpt": item.text,
                "score": item.score,
            }
            for item in evidence
        ],
        "findings": [
            {
                "level": item.level,
                "title": item.title,
                "rationale": item.rationale,
                "recommendation": item.recommendation,
                "evidence_ids": item.evidence_ids,
            }
            for item in findings
        ],
    }


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
