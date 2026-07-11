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
