from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？；.!?;])")


def build_chunks(
    document_id: str,
    sections: Iterable[dict[str, Any]],
    max_chars: int = 480,
    overlap_chars: int = 80,
) -> list[dict[str, Any]]:
    """Convert parser sections into retrievable records without losing source location."""
    chunks: list[dict[str, Any]] = []
    for section in sections:
        text = str(section["text"]).strip()
        if not text:
            continue
        location = dict(section.get("location", {}))
        parts = [text] if location.get("kind") == "table_row" else split_text(text, max_chars, overlap_chars)
        for part in parts:
            chunks.append(
                {
                    "id": f"{document_id}-chunk-{len(chunks) + 1}",
                    "text": part,
                    "location": location,
                }
            )
    return chunks


def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sentences = [item.strip() for item in SENTENCE_BOUNDARY.split(text) if item.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current)
            current = current[-overlap_chars:] + sentence
        else:
            current += sentence
    if current:
        chunks.append(current)
    return chunks or [text]


def format_location(location: dict[str, Any]) -> str:
    kind = location.get("kind", "document")
    if kind == "page":
        return f"第 {location['page_number']} 页"
    if kind == "paragraph":
        return f"第 {location['paragraph_number']} 段"
    if kind == "table_row":
        return f"表格 {location['table_number']}，第 {location['row_number']} 行"
    if kind == "sheet_row":
        return f"工作表：{location['sheet_name']}，第 {location['row_number']} 行"
    if kind == "lines":
        start, end = location["start_line"], location["end_line"]
        return f"第 {start} 行" if start == end else f"第 {start}-{end} 行"
    return "整篇文档"
