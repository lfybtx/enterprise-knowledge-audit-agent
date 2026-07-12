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
