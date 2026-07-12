from app.services.embeddings import embed_text
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
