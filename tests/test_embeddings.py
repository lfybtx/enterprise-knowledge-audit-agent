import httpx

from app.services.embeddings import EmbeddingProviderError, download_local_embedding_model, embed_query, embed_text, embed_texts
from app.vector_utils import EMBEDDING_DIMENSIONS, vector_literal


def test_embed_text_is_deterministic_and_normalized():
    first = embed_text("Regional manager approval is required before export.")
    second = embed_text("Regional manager approval is required before export.")

    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert round(sum(value * value for value in first), 6) == 1.0


def test_empty_embedding_keeps_expected_dimensions():
    embedding = embed_text("")

    assert embedding == [0.0] * EMBEDDING_DIMENSIONS


def test_vector_literal_uses_pgvector_format():
    assert vector_literal([0.5, -0.25]) == "[0.50000000,-0.25000000]"


def test_openai_compatible_embedding_uses_configured_dimensions(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"index": 1, "embedding": [0.2] * 512}, {"index": 0, "embedding": [0.1] * 512}]},
        )

    monkeypatch.setattr("app.services.embeddings.httpx.post", fake_post)

    vectors = embed_texts(["first", "second"])

    assert captured["url"].endswith("/v1/embeddings")
    assert captured["payload"]["dimensions"] == 512
    assert vectors == [[0.1] * 512, [0.2] * 512]


def test_openai_compatible_embedding_rejects_wrong_vector_length(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_post(url, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", url), json={"data": [{"index": 0, "embedding": [0.1]}]})

    monkeypatch.setattr("app.services.embeddings.httpx.post", fake_post)

    try:
        embed_text("wrong dimensions")
    except EmbeddingProviderError as error:
        assert "512 dimensions" in str(error)
    else:
        raise AssertionError("Expected wrong embedding dimensions to fail")


def test_local_hf_embedding_uses_bge_query_instruction(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "local-hf")
    captured = {}

    class FakeVectorResult:
        def tolist(self):
            return [[0.5] * 512]

    class FakeModel:
        def encode(self, inputs, **kwargs):
            captured["inputs"] = inputs
            captured["kwargs"] = kwargs
            return FakeVectorResult()

    monkeypatch.setattr("app.services.embeddings._load_local_sentence_transformer", lambda _: FakeModel())

    vector = embed_query("客户名单导出需要审批吗")

    assert len(vector) == 512
    assert captured["inputs"][0].startswith("为这个句子生成表示")
    assert captured["kwargs"]["normalize_embeddings"] is True


def test_local_hf_model_download_uses_configured_model(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    captured = {}

    def fake_load(model_name):
        captured["model_name"] = model_name

    monkeypatch.setattr("app.services.embeddings._load_local_sentence_transformer", fake_load)

    assert download_local_embedding_model() == "BAAI/bge-small-zh-v1.5"
    assert captured["model_name"] == "BAAI/bge-small-zh-v1.5"
