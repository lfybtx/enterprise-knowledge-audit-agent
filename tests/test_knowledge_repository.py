import pytest


try:
    from app.repositories.knowledge_repository import document_to_record
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
