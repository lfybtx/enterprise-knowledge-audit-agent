from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.audit import assess
from app.services.retrieval import HybridRetriever, grounded_answer


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = ROOT / "app" / "data" / "sample_documents.json"


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
        return json.load(file)


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
    global retriever
    document = {"id": str(uuid4()), **payload.model_dump()}
    documents.append(document)
    retriever = HybridRetriever(documents)
    audit_log.append({"event": "document_ingested", "document_id": document["id"]})
    return {"id": document["id"], "message": "Document indexed"}


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
