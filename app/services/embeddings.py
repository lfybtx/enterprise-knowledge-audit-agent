from __future__ import annotations

import hashlib
import math
import os
from functools import lru_cache
from typing import Any

import httpx

from app.services.model_provider import (
    DEFAULT_LOCAL_EMBEDDING_MODEL,
    LOCAL_HF_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
    ModelConfigurationError,
    ModelProviderSettings,
)
from app.services.retrieval import tokenize
from app.vector_utils import EMBEDDING_DIMENSIONS


class EmbeddingProviderError(RuntimeError):
    """Raised when a configured embedding provider cannot return usable vectors."""


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return embed_texts([text], dimensions=dimensions)[0]


def embed_query(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return embed_texts([text], dimensions=dimensions, is_query=True)[0]


def download_local_embedding_model() -> str:
    """Download the configured local model into MODEL_CACHE_DIR and return its name."""
    model_name = os.getenv("LOCAL_EMBEDDING_MODEL", DEFAULT_LOCAL_EMBEDDING_MODEL).strip()
    if not model_name:
        raise EmbeddingProviderError("LOCAL_EMBEDDING_MODEL cannot be empty")
    _load_local_sentence_transformer(model_name)
    return model_name


def embed_texts(
    texts: list[str],
    dimensions: int = EMBEDDING_DIMENSIONS,
    *,
    is_query: bool = False,
) -> list[list[float]]:
    """Embed a batch with the selected provider while preserving local fallback."""
    if not texts:
        return []

    try:
        settings = ModelProviderSettings.from_environment()
    except ModelConfigurationError as error:
        raise EmbeddingProviderError(str(error)) from error

    if settings.provider == OPENAI_COMPATIBLE_PROVIDER:
        return _embed_with_openai_compatible(settings, texts, dimensions)
    if settings.provider == LOCAL_HF_PROVIDER:
        return _embed_with_local_hf(settings, texts, dimensions, is_query=is_query)
    return [_local_embed_text(text, dimensions) for text in texts]


def _local_embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a deterministic local embedding for development and repeatable tests.

    This is a lightweight hashed embedding. It gives us the same persistence and
    pgvector workflow as a model-backed embedding provider, while keeping the
    project runnable without API keys or large local model downloads.
    """
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def _embed_with_openai_compatible(
    settings: ModelProviderSettings,
    texts: list[str],
    dimensions: int,
) -> list[list[float]]:
    if settings.embedding_dimensions != dimensions:
        raise EmbeddingProviderError(
            f"Configured embedding dimensions ({settings.embedding_dimensions}) do not match pgvector dimensions ({dimensions})"
        )

    request_payload: dict[str, Any] = {
        "model": settings.embedding_model,
        "input": texts,
        "dimensions": dimensions,
        "encoding_format": "float",
    }
    try:
        response = httpx.post(
            f"{settings.base_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json=request_payload,
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as error:
        raise EmbeddingProviderError(f"Embedding provider request failed: {error}") from error
    except ValueError as error:
        raise EmbeddingProviderError("Embedding provider returned invalid JSON") from error

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or len(entries) != len(texts):
        raise EmbeddingProviderError("Embedding provider returned an unexpected number of vectors")

    vectors: list[list[float]] = []
    for entry in sorted(entries, key=lambda item: item.get("index", -1)):
        vector = entry.get("embedding") if isinstance(entry, dict) else None
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise EmbeddingProviderError(f"Embedding provider must return vectors with {dimensions} dimensions")
        vectors.append([float(value) for value in vector])
    return vectors


def _embed_with_local_hf(
    settings: ModelProviderSettings,
    texts: list[str],
    dimensions: int,
    *,
    is_query: bool,
) -> list[list[float]]:
    if settings.embedding_dimensions != dimensions:
        raise EmbeddingProviderError(
            f"Configured embedding dimensions ({settings.embedding_dimensions}) do not match pgvector dimensions ({dimensions})"
        )
    model = _load_local_sentence_transformer(settings.embedding_model or "")
    inputs = [_bge_query_instruction(text) for text in texts] if is_query else texts
    try:
        result = model.encode(inputs, normalize_embeddings=True, show_progress_bar=False)
        vectors = result.tolist()
    except Exception as error:
        raise EmbeddingProviderError(f"Local embedding model failed: {error}") from error
    if len(vectors) != len(texts) or any(len(vector) != dimensions for vector in vectors):
        raise EmbeddingProviderError(f"Local embedding model must return vectors with {dimensions} dimensions")
    return [[float(value) for value in vector] for vector in vectors]


def _bge_query_instruction(text: str) -> str:
    return f"为这个句子生成表示以用于检索相关文章：{text}"


@lru_cache(maxsize=2)
def _load_local_sentence_transformer(model_name: str):
    cache_dir = os.getenv("MODEL_CACHE_DIR") or None
    if cache_dir:
        os.environ.setdefault("HF_HOME", cache_dir)
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise EmbeddingProviderError(
            "Local embedding dependencies are missing. Install requirements-local-models.txt or rebuild the Docker image."
        ) from error
    try:
        return SentenceTransformer(model_name, cache_folder=cache_dir)
    except Exception as error:
        raise EmbeddingProviderError(f"Unable to download or load local embedding model '{model_name}': {error}") from error
