from __future__ import annotations

from pathlib import Path

from app.services.chunking import build_chunks
from app.services.object_storage import store_upload
from app.services.parsers import parse_document_sections


def process_upload(payload: dict) -> dict:
    from app.main import UPLOAD_DIR, add_document, persist_or_save_runtime, selected_knowledge_base_uuid
    raw = Path(payload["temp_path"]).read_bytes()
    parsed = parse_document_sections(payload["filename"], raw)
    stored = store_upload(content=raw, filename=payload["filename"], object_id=payload["document_id"], content_type=payload.get("content_type", "application/octet-stream"), fallback_dir=UPLOAD_DIR)
    document = {"id": payload["document_id"], "title": payload["title"], "source": stored.source, "file_type": parsed.file_type, "content": parsed.text,
                "chunks": build_chunks(payload["document_id"], [{"text": s.text, "location": s.location} for s in parsed.sections])}
    kb = selected_knowledge_base_uuid(payload.get("knowledge_base_id"))
    if kb: document["knowledge_base_id"] = str(kb)
    add_document(persist_or_save_runtime(document, payload["requested_by"]))
    Path(payload["temp_path"]).unlink(missing_ok=True)
    return {"processed_count": len(document["chunks"])}


HANDLERS = {"upload": process_upload}


def process_evaluation(payload: dict) -> dict:
    from app.main import EvaluationCase, user_documents
    from app.services.retrieval import HybridRetriever
    outcomes = []
    for case in payload["cases"]:
        item = EvaluationCase.model_validate(case)
        hits = HybridRetriever(user_documents(payload["requested_by"])).search(item.question, limit=1)
        actual = hits[0].document_id if hits else None
        outcomes.append({"question": item.question, "expected_document_id": item.expected_document_id, "actual_document_id": actual, "passed": actual == item.expected_document_id})
    passed = sum(item["passed"] for item in outcomes)
    return {"total": len(outcomes), "passed": passed, "recall_at_1": round(passed / len(outcomes), 3), "outcomes": outcomes, "processed_count": len(outcomes)}


HANDLERS["evaluation"] = process_evaluation
