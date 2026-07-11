from fastapi.testclient import TestClient

import app.main as main
from app.services.retrieval import HybridRetriever


client = TestClient(main.app)


def test_upload_txt_document_is_indexed(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "RUNTIME_DOCUMENTS_PATH", tmp_path / "documents.json")

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
    finally:
        main.documents[:] = [document for document in main.documents if document["id"] != document_id]
        main.retriever = HybridRetriever(main.documents)
