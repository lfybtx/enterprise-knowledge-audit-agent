from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from app.services.chunking import build_chunks, format_location


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")


def tokenize(text: str) -> list[str]:
    """Return overlapping Chinese n-grams plus regular word tokens."""
    text = text.lower()
    tokens = TOKEN_PATTERN.findall(text)
    chinese = "".join(char for char in text if "\u4e00" <= char <= "\u9fff")
    tokens.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return tokens


def split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。！？；\n]", text) if item.strip()]


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    title: str
    source: str
    text: str
    location: dict[str, Any]
    score: float
    lexical_score: float | None = None
    semantic_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None

    @property
    def location_label(self) -> str:
        return format_location(self.location)


class HybridRetriever:
    """Small local retriever that combines BM25-like lexical and cosine scores."""

    def __init__(self, documents: Iterable[dict[str, Any]]) -> None:
        self.documents = list(documents)
        self.chunks = [chunk for document in self.documents for chunk in self._document_chunks(document)]
        self._doc_terms = [Counter(tokenize(chunk["text"])) for chunk in self.chunks]
        self._doc_lengths = [sum(terms.values()) for terms in self._doc_terms]
        self._avg_length = sum(self._doc_lengths) / max(1, len(self._doc_lengths))
        self._idf = self._build_idf()

    def _build_idf(self) -> dict[str, float]:
        document_count = len(self.documents)
        occurrences: Counter[str] = Counter()
        for terms in self._doc_terms:
            occurrences.update(terms.keys())
        return {
            term: math.log(1 + (document_count - count + 0.5) / (count + 0.5))
            for term, count in occurrences.items()
        }

    def search(self, question: str, limit: int = 3) -> list[RetrievedChunk]:
        query_terms = Counter(tokenize(question))
        if not query_terms:
            return []

        results: list[RetrievedChunk] = []
        for chunk, terms, length in zip(self.chunks, self._doc_terms, self._doc_lengths):
            lexical = self._bm25(query_terms, terms, length)
            semantic = self._cosine(query_terms, terms)
            score = 0.72 * lexical + 0.28 * semantic + self._domain_boost(question, chunk)
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["id"],
                    document_id=chunk["document_id"],
                    title=chunk["title"],
                    source=chunk["source"],
                    text=chunk["text"],
                    location=chunk["location"],
                    score=round(score, 4),
                )
            )
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _document_chunks(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        source_chunks = document.get("chunks")
        if not source_chunks:
            source_chunks = build_chunks(
                document["id"],
                [{"text": document["content"], "location": {"kind": "document"}}],
            )
        return [
            {
                "id": chunk["id"],
                "document_id": document["id"],
                "title": document["title"],
                "source": document["source"],
                "text": chunk["text"],
                "location": chunk.get("location", {"kind": "document"}),
            }
            for chunk in source_chunks
        ]

    @staticmethod
    def _domain_boost(question: str, chunk: dict[str, Any]) -> float:
        """Boost exact business-action matches that are critical for audit retrieval."""
        searchable_text = f"{chunk['title']} {chunk['text']}"
        boost = 0.0
        if "导出" in question and "导出" in chunk["title"]:
            boost += 2.2
        if "客户" in question and "客户" in chunk["title"]:
            boost += 0.8
        if "旧版" in question and ("旧版" in searchable_text or "历史" in searchable_text):
            boost += 1.5
        return boost

    def _bm25(self, query_terms: Counter[str], document_terms: Counter[str], length: int) -> float:
        k1, b = 1.5, 0.75
        total = 0.0
        for term, frequency in query_terms.items():
            document_frequency = document_terms.get(term, 0)
            if not document_frequency:
                continue
            numerator = document_frequency * (k1 + 1)
            denominator = document_frequency + k1 * (1 - b + b * length / self._avg_length)
            total += self._idf.get(term, 0.0) * numerator / denominator * frequency
        return total

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        overlap = sum(left[key] * right.get(key, 0) for key in left)
        if not overlap:
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        return overlap / (left_norm * right_norm)


def grounded_answer(question: str, evidence: list[RetrievedChunk]) -> str:
    """Produce a deterministic answer from the highest-overlap source sentences."""
    query_terms = set(tokenize(question))
    candidates: list[tuple[int, str, int]] = []
    for evidence_index, chunk in enumerate(evidence):
        for sentence in split_sentences(chunk.text):
            overlap = len(query_terms.intersection(tokenize(sentence)))
            if overlap:
                candidates.append((overlap, sentence, evidence_index))
    candidates.sort(key=lambda item: item[0], reverse=True)

    selected: list[tuple[str, int]] = []
    for _, sentence, evidence_index in candidates:
        if sentence not in [item[0] for item in selected]:
            selected.append((sentence, evidence_index))
        if len(selected) == 3:
            break

    if not selected:
        return "当前知识库没有足够证据回答这个问题。建议补充相关制度文件后再查询。"

    answer = "根据已检索到的制度文件：\n" + "\n".join(
        f"{index + 1}. {sentence} [证据{evidence_index + 1}]"
        for index, (sentence, evidence_index) in enumerate(selected)
    )
    return answer
