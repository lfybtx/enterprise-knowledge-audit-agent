import sys
from types import SimpleNamespace

from app.services.reranking import _load_local_cross_encoder, rerank_candidates, rerank_chunks
from app.services.retrieval import RetrievedChunk


def _chunk(identifier: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=identifier,
        document_id=f"document-{identifier}",
        title=f"Document {identifier}",
        source=f"{identifier}.txt",
        text=f"Evidence for {identifier}",
        location={"kind": "document"},
        score=score,
        fusion_score=score,
    )


def test_reranker_reorders_fused_candidates(monkeypatch):
    monkeypatch.setenv("RERANKER_ENABLED", "true")

    class FakeModel:
        def predict(self, pairs, **kwargs):
            assert len(pairs) == 2
            return [0.1, 0.9]

    monkeypatch.setattr("app.services.reranking._load_local_cross_encoder", lambda _: FakeModel())

    results = rerank_chunks("question", [_chunk("first", 0.9), _chunk("second", 0.4)], limit=2)

    assert [item.chunk_id for item in results] == ["second", "first"]
    assert results[0].rerank_score == 0.9
    assert results[0].fusion_score == 0.4


def test_reranker_keeps_discarded_candidates_for_trace(monkeypatch):
    monkeypatch.setenv("RERANKER_ENABLED", "true")

    class FakeModel:
        def predict(self, pairs, **kwargs):
            return [0.1, 0.9]

    monkeypatch.setattr("app.services.reranking._load_local_cross_encoder", lambda _: FakeModel())

    candidates = rerank_candidates("question", [_chunk("first", 0.9), _chunk("second", 0.4)])

    assert [item.chunk_id for item in candidates] == ["second", "first"]
    assert all(item.rerank_score is not None for item in candidates)


def test_reranker_falls_back_to_fusion_order_when_model_fails(monkeypatch):
    monkeypatch.setenv("RERANKER_ENABLED", "true")

    def raise_error(_):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.services.reranking._load_local_cross_encoder", raise_error)

    results = rerank_chunks("question", [_chunk("first", 0.9), _chunk("second", 0.4)], limit=2)

    assert [item.chunk_id for item in results] == ["first", "second"]
    assert all(item.rerank_score is None for item in results)


def test_cross_encoder_uses_hugging_face_cache_directory(monkeypatch):
    monkeypatch.setenv("MODEL_CACHE_DIR", "/app/data/models")
    monkeypatch.delenv("HF_HOME", raising=False)
    _load_local_cross_encoder.cache_clear()
    captured = {}

    class FakeCrossEncoder:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured["kwargs"] = kwargs

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=FakeCrossEncoder))

    _load_local_cross_encoder("test-reranker")

    assert captured["kwargs"] == {}
    assert captured["model_name"] == "test-reranker"
    assert __import__("os").environ["HF_HOME"] == "/app/data/models"
    _load_local_cross_encoder.cache_clear()
