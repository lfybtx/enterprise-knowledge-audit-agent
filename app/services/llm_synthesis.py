from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.services.audit import AuditFinding
from app.services.model_provider import ChatProviderSettings, OPENAI_COMPATIBLE_PROVIDER, ModelConfigurationError
from app.services.retrieval import RetrievedChunk


class LlmSynthesisError(RuntimeError):
    """Raised when a remote chat model cannot produce a valid grounded answer."""


@dataclass(frozen=True)
class LlmSynthesisResult:
    answer: str
    input_tokens: int
    output_tokens: int
    trace_data: dict[str, Any]


def synthesize_answer(
    *,
    question: str,
    evidence: list[RetrievedChunk],
    findings: list[AuditFinding],
) -> Optional[LlmSynthesisResult]:
    """Optionally synthesize a strict JSON answer with an OpenAI-compatible chat model.

    The default local providers return None so the rule-based grounded answer remains
    fully offline and deterministic.
    """
    try:
        settings = ChatProviderSettings.from_environment()
    except ModelConfigurationError as error:
        raise LlmSynthesisError(str(error)) from error

    if settings.provider != OPENAI_COMPATIBLE_PROVIDER:
        return None
    if not evidence:
        return None

    prompt = build_synthesis_prompt(question, evidence, findings)
    payload = {
        "model": settings.chat_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an enterprise knowledge-base audit agent. "
                    "Return only valid JSON. Never answer without using the supplied evidence."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            f"{settings.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json=payload,
            timeout=45.0,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as error:
        raise LlmSynthesisError(f"Chat provider request failed: {error}") from error
    except ValueError as error:
        raise LlmSynthesisError("Chat provider returned invalid JSON") from error

    content = _extract_message_content(body)
    parsed = _parse_strict_json(content)
    answer = str(parsed["answer"]).strip()
    return LlmSynthesisResult(
        answer=answer,
        input_tokens=_usage_token(body, "prompt_tokens", _estimate_tokens(prompt)),
        output_tokens=_usage_token(body, "completion_tokens", _estimate_tokens(answer)),
        trace_data={
            "provider": settings.provider,
            "chat_model": settings.chat_model,
            "schema": "audit_answer_v1",
            "answer_source": "openai_compatible_chat",
            "citation_count": len(parsed["citations"]),
        },
    )


def build_synthesis_prompt(question: str, evidence: list[RetrievedChunk], findings: list[AuditFinding]) -> str:
    evidence_lines = []
    for index, item in enumerate(evidence[:5], start=1):
        evidence_lines.append(
            f"[Evidence {index}] document_id={item.document_id}; title={item.title}; "
            f"location={item.location_label}; text={item.text}"
        )
    finding_lines = [
        f"- level={finding.level}; title={finding.title}; rationale={finding.rationale}; recommendation={finding.recommendation}"
        for finding in findings[:5]
    ]
    return (
        f"Question:\n{question}\n\n"
        f"Evidence:\n" + "\n".join(evidence_lines) + "\n\n"
        f"Risk findings:\n" + ("\n".join(finding_lines) or "- none") + "\n\n"
        "Return JSON with exactly this shape:\n"
        '{"answer":"string grounded in evidence","citations":[{"document_id":"string","evidence_index":1}],"risk_summary":"string"}'
    )


def _extract_message_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmSynthesisError("Chat provider returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LlmSynthesisError("Chat provider returned an empty message")
    return content


def _parse_strict_json(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except ValueError as error:
        raise LlmSynthesisError("Chat provider message is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise LlmSynthesisError("Chat provider JSON must be an object")
    if not isinstance(parsed.get("answer"), str) or not parsed["answer"].strip():
        raise LlmSynthesisError("Chat provider JSON must include a non-empty answer")
    citations = parsed.get("citations")
    if not isinstance(citations, list) or not citations:
        raise LlmSynthesisError("Chat provider JSON must include at least one citation")
    for citation in citations:
        if not isinstance(citation, dict) or not citation.get("document_id"):
            raise LlmSynthesisError("Each citation must include document_id")
    return parsed


def _usage_token(body: dict[str, Any], key: str, fallback: int) -> int:
    usage = body.get("usage")
    if isinstance(usage, dict) and isinstance(usage.get(key), int):
        return usage[key]
    return fallback


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
