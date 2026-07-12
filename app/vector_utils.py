from __future__ import annotations


EMBEDDING_DIMENSIONS = 64


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
