from fastapi.testclient import TestClient

import app.main as main
from app.services.retrieval import HybridRetriever


client = TestClient(main.app)


def test_list_documents_returns_numeric_chunk_count():
    response = client.get("/api/documents")

    assert response.status_code == 200
    assert all(isinstance(document["chunk_count"], int) for document in response.json())


def test_upload_txt_document_is_indexed(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "RUNTIME_DOCUMENTS_PATH", tmp_path / "documents.json")
    original_documents = list(main.documents)
    original_retriever = main.retriever
    main.documents[:] = main.load_documents()
    main.retriever = HybridRetriever(main.documents)

    response = client.post(
        "/api/documents/upload",
        data={"title": "客户名单导出补充规范"},
        files={
            "file": (
                "export-policy.txt",
                "客户名单导出必须由区域经理审批，导出文件保存不得超过 7 天。",
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    document_id = response.json()["id"]

    try:
        hits = main.retriever.search("客户名单导出需要区域经理审批吗？", limit=1)
        assert hits[0].document_id == document_id
        assert hits[0].location_label == "第 1 行"
    finally:
        main.documents[:] = original_documents
        main.retriever = original_retriever


def test_runtime_documents_are_isolated_by_user_header(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "RUNTIME_DOCUMENTS_PATH", tmp_path / "documents.json")
    original_documents = list(main.documents)
    original_retriever = main.retriever
    main.documents[:] = []
    main.retriever = HybridRetriever(main.documents)

    response = client.post(
        "/api/documents",
        headers={"X-User-Id": "demo-alice"},
        json={
            "title": "Alice export policy",
            "source": "alice-policy.txt",
            "content": "Alice private export approval requires manager review before customer data is shared.",
        },
    )

    assert response.status_code == 201
    document_id = response.json()["id"]

    try:
        alice_documents = client.get("/api/documents", headers={"X-User-Id": "demo-alice"}).json()
        bob_documents = client.get("/api/documents", headers={"X-User-Id": "demo-bob"}).json()
        bob_answer = client.post(
            "/api/ask",
            headers={"X-User-Id": "demo-bob"},
            json={"question": "Does Alice export require manager review?"},
        )

        assert [document["id"] for document in alice_documents] == [document_id]
        assert bob_documents == []
        assert bob_answer.status_code == 404
    finally:
        main.documents[:] = original_documents
        main.retriever = original_retriever


def test_current_user_endpoint_reflects_user_header():
    response = client.get("/api/me", headers={"X-User-Id": "demo-alice"})

    assert response.status_code == 200
    assert response.json() == {"id": "demo-alice", "display_name": "Alice"}


def test_audit_log_is_filtered_by_user_header():
    original_audit_log = list(main.audit_log)
    main.audit_log[:] = [
        {"event": "question_answered", "user_id": "demo-alice"},
        {"event": "question_answered", "user_id": "demo-bob"},
        {"event": "legacy_event_without_user"},
    ]

    try:
        alice_response = client.get("/api/audit-log", headers={"X-User-Id": "demo-alice"})
        bob_response = client.get("/api/audit-log", headers={"X-User-Id": "demo-bob"})
        local_response = client.get("/api/audit-log")

        assert alice_response.json() == [{"event": "question_answered", "user_id": "demo-alice"}]
        assert bob_response.json() == [{"event": "question_answered", "user_id": "demo-bob"}]
        assert local_response.json() == [{"event": "legacy_event_without_user"}]
    finally:
        main.audit_log[:] = original_audit_log


def test_persist_audit_event_includes_workflow_trace():
    original_audit_log = list(main.audit_log)
    main.audit_log[:] = []

    try:
        main.persist_audit_event(
            event_type="question_answered",
            user_external_id="demo-alice",
            question="Can customer data be exported?",
            response={
                "trace_id": "trace-1",
                "answer": "Customer data requires approval.",
                "report": {"summary": "Customer data requires approval."},
                "citations": [{"document_id": "doc-1"}],
                "findings": [{"level": "High"}],
                "workflow_trace": [
                    {
                        "name": "retrieval_agent",
                        "status": "completed",
                        "detail": "retrieved 1 evidence chunk",
                        "duration_ms": 11,
                        "prompt": "Question: Can customer data be exported?",
                        "tool_calls": ["evidence_loader"],
                        "input_tokens": 10,
                        "output_tokens": 24,
                        "failure_reason": None,
                    }
                ],
            },
        )

        assert main.audit_log[-1]["workflow_trace"][0]["name"] == "retrieval_agent"
        assert main.audit_log[-1]["step_count"] == 1
    finally:
        main.audit_log[:] = original_audit_log
