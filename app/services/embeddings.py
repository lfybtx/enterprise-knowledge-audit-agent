from __future__ import annotations

import hashlib
import math

from app.services.retrieval import tokenize
from app.vector_utils import EMBEDDING_DIMENSIONS


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
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
