from __future__ import annotations

from typing import Any

from sqlalchemy.types import UserDefinedType

from app.vector_utils import EMBEDDING_DIMENSIONS, vector_literal


class Vector(UserDefinedType):
    """Minimal pgvector SQLAlchemy type without adding a Python pgvector dependency."""

    cache_ok = True

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any):
        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return vector_literal(value)

        return process
