import pytest


try:
    from app.repositories.knowledge_repository import document_to_record, merge_search_results
    from app.services.retrieval import RetrievedChunk
except ModuleNotFoundError:
    pytest.skip("SQLAlchemy is not installed in this environment", allow_module_level=True)


class FakeChunk:
    def __init__(self, identifier, index, text, location):
        self.id = identifier
        self.chunk_index = index
        self.text = text
        self.location = location


class FakeDocument:
    id = "document-1"
    title = "Export policy"
    source = "export-policy.txt"
    file_type = "txt"
    content = "Manager approval is required."
    chunks = [
        FakeChunk("chunk-2", 2, "Keep the file for seven days.", {"kind": "lines", "start_line": 2, "end_line": 2}),
        FakeChunk("chunk-1", 1, "Manager approval is required.", {"kind": "lines", "start_line": 1, "end_line": 1}),
    ]


def test_document_to_record_orders_chunks_by_chunk_index():
    record = document_to_record(FakeDocument())

    assert record["id"] == "document-1"
    assert [chunk["id"] for chunk in record["chunks"]] == ["chunk-1", "chunk-2"]


def test_merge_search_results_combines_lexical_and_semantic_scores():
    lexical = RetrievedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="Export policy",
        source="policy.txt",
        text="Approval is required.",
        location={"kind": "document"},
        score=4.0,
    )
    semantic = RetrievedChunk(
        chunk_id="chunk-2",
        document_id="doc-2",
        title="Retention policy",
        source="retention.txt",
        text="Files must be deleted after seven days.",
        location={"kind": "document"},
        score=0.95,
    )

    results = merge_search_results([lexical], [semantic], limit=2)

    assert {result.chunk_id for result in results} == {"chunk-1", "chunk-2"}
    assert all(0 < result.score <= 1 for result in results)
