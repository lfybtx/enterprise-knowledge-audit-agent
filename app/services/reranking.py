"""Local cross-encoder reranking for hybrid retrieval candidates."""
from __future__ import annotations

import os
from dataclasses import replace
from functools import lru_cache

from app.services.retrieval import RetrievedChunk


DEFAULT_LOCAL_RERANKER_MODEL = "BAAI/bge-reranker-base"


class RerankerError(RuntimeError):
    """Raised when local reranking cannot be completed."""


def rerank_chunks(question: str, candidates: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    """Rerank a bounded candidate set, falling back to fusion ranking on failure."""
    return rerank_candidates(question, candidates)[:limit]


def rerank_candidates(question: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Return the complete candidate ranking so discarded candidates are explainable."""
    if len(candidates) < 2 or not _reranker_enabled():
        return candidates

    try:
        model = _load_local_cross_encoder(_reranker_model_name())
        scores = model.predict([(question, chunk.text) for chunk in candidates], show_progress_bar=False)
        reranked = [
            replace(chunk, score=round(float(score), 4), rerank_score=round(float(score), 4))
            for chunk, score in zip(candidates, scores)
        ]
        return sorted(reranked, key=lambda chunk: chunk.score, reverse=True)
    except Exception:
        # Retrieval remains available even when the optional local model is unavailable.
        return candidates


def download_local_reranker_model() -> str:
    """Download the configured reranker into MODEL_CACHE_DIR and return its name."""
    model_name = _reranker_model_name()
    _load_local_cross_encoder(model_name)
    return model_name


def _reranker_enabled() -> bool:
    return os.getenv("RERANKER_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _reranker_model_name() -> str:
    return os.getenv("LOCAL_RERANKER_MODEL", DEFAULT_LOCAL_RERANKER_MODEL).strip() or DEFAULT_LOCAL_RERANKER_MODEL


@lru_cache(maxsize=1)
def _load_local_cross_encoder(model_name: str):
    cache_dir = os.getenv("MODEL_CACHE_DIR") or None
    if cache_dir:
        os.environ.setdefault("HF_HOME", cache_dir)
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as error:
        raise RerankerError(
            "Local reranker dependencies are missing. Install requirements-local-models.txt or rebuild the Docker image."
        ) from error
    try:
        return CrossEncoder(model_name)
    except Exception as error:
        raise RerankerError(f"Unable to download or load local reranker model '{model_name}': {error}") from error
