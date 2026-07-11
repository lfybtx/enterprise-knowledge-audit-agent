import json
from pathlib import Path

from app.services.audit import assess
from app.services.retrieval import HybridRetriever


ROOT = Path(__file__).resolve().parents[1]


def load_documents():
    with (ROOT / "app" / "data" / "sample_documents.json").open(encoding="utf-8") as file:
        return json.load(file)


def test_retrieval_finds_export_policy():
    retriever = HybridRetriever(load_documents())
    result = retriever.search("客户数据导出前需要什么审批？", limit=1)
    assert result[0].document_id == "sales-export-v2"


def test_legacy_policy_is_flagged_as_conflict():
    retriever = HybridRetriever(load_documents())
    evidence = retriever.search("旧版系统直接下载完整客户清单是否符合现行制度？")
    findings = assess("旧版系统直接下载完整客户清单是否符合现行制度？", evidence)
    assert any("冲突" in finding.title for finding in findings)


def test_retrieval_returns_precise_chunk_location():
    documents = [
        {
            "id": "export-sheet",
            "title": "客户导出审批表",
            "source": "审批表.xlsx",
            "content": "客户导出审批记录",
            "chunks": [
                {
                    "id": "export-sheet-chunk-1",
                    "text": "审批人: 区域经理 | 保存期限: 7 天",
                    "location": {"kind": "sheet_row", "sheet_name": "客户导出", "row_number": 4},
                }
            ],
        }
    ]

    result = HybridRetriever(documents).search("客户导出需要谁审批？", limit=1)[0]

    assert result.chunk_id == "export-sheet-chunk-1"
    assert result.location_label == "工作表：客户导出，第 4 行"
