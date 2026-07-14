from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from uuid import uuid4
from time import perf_counter
from typing import Any, Callable, Iterable

from app.services.audit import AuditFinding, assess
from app.services.llm_synthesis import LlmSynthesisError, synthesize_answer
from app.services.retrieval import RetrievedChunk, grounded_answer


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    status: str
    detail: str
    duration_ms: int


@dataclass(frozen=True)
class WorkflowTraceEntry:
    name: str
    status: str
    detail: str
    duration_ms: int
    prompt: str
    tool_calls: list[str]
    input_tokens: int
    output_tokens: int
    failure_reason: str | None
    trace_data: dict[str, Any] = field(default_factory=dict)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _make_prompt(question: str, evidence: list[RetrievedChunk], findings: list[AuditFinding], step_name: str) -> str:
    if step_name == "retrieval_agent":
        return f"Question: {question}"
    if step_name == "audit_agent":
        titles = "; ".join(chunk.title for chunk in evidence[:3]) or "no evidence"
        return f"Question: {question}\nEvidence titles: {titles}\nEvidence count: {len(evidence)}"
    titles = "; ".join(finding.title for finding in findings[:5]) or "no findings"
    return f"Question: {question}\nFindings: {titles}\nEvidence count: {len(evidence)}"


def _run_sequential_workflow(
    question: str,
    evidence_loader: Callable[[str], list[RetrievedChunk] | tuple[list[RetrievedChunk], dict[str, Any]]],
) -> dict[str, Any]:
    workflow_steps: list[WorkflowStep] = []
    workflow_trace: list[WorkflowTraceEntry] = []
    trace_id = str(uuid4())

    start = perf_counter()
    loaded_evidence = evidence_loader(question)
    if isinstance(loaded_evidence, tuple):
        evidence, retrieval_diagnostics = loaded_evidence
    else:
        evidence, retrieval_diagnostics = loaded_evidence, {}
    retrieval_prompt = _make_prompt(question, evidence, [], "retrieval_agent")
    retrieval_detail = _retrieval_detail(len(evidence), retrieval_diagnostics)
    retrieval_tools = ["evidence_loader"]
    if retrieval_diagnostics:
        retrieval_tools = ["keyword_search", "pgvector_search", "fusion"]
        if retrieval_diagnostics.get("reranker_applied"):
            retrieval_tools.append("local_reranker")
    workflow_steps.append(
        WorkflowStep(
            name="retrieval_agent",
            status="completed" if evidence else "empty",
            detail=retrieval_detail,
            duration_ms=_elapsed_ms(start),
        )
    )
    workflow_trace.append(
        WorkflowTraceEntry(
            name="retrieval_agent",
            status="completed" if evidence else "empty",
            detail=retrieval_detail,
            duration_ms=workflow_steps[-1].duration_ms,
            prompt=retrieval_prompt,
            tool_calls=retrieval_tools,
            input_tokens=_estimate_tokens(retrieval_prompt),
            output_tokens=max(1, len(evidence) * 24),
            failure_reason=None if evidence else "No evidence returned by retrieval stage",
            trace_data={"retrieval": retrieval_diagnostics},
        )
    )

    start = perf_counter()
    findings = assess(question, evidence)
    audit_prompt = _make_prompt(question, evidence, findings, "audit_agent")
    workflow_steps.append(
        WorkflowStep(
            name="audit_agent",
            status="completed" if findings else "empty",
            detail=f"generated {len(findings)} findings",
            duration_ms=_elapsed_ms(start),
        )
    )
    workflow_trace.append(
        WorkflowTraceEntry(
            name="audit_agent",
            status="completed" if findings else "empty",
            detail=f"generated {len(findings)} findings",
            duration_ms=workflow_steps[-1].duration_ms,
            prompt=audit_prompt,
            tool_calls=["assess"],
            input_tokens=_estimate_tokens(audit_prompt),
            output_tokens=max(1, len(findings) * 36),
            failure_reason=None if findings else "No findings were produced",
        )
    )

    start = perf_counter()
    report = build_risk_report(question, evidence, findings)
    answer = grounded_answer(question, evidence)
    report_tools = ["build_risk_report"]
    report_trace_data: dict[str, Any] = {}
    report_failure_reason = None
    llm_input_tokens = 0
    llm_output_tokens = 0
    try:
        llm_result = synthesize_answer(question=question, evidence=evidence, findings=findings)
    except LlmSynthesisError as error:
        llm_result = None
        report_failure_reason = str(error)
        report_trace_data["llm"] = {"status": "fallback", "failure_reason": str(error)}
    if llm_result is not None:
        answer = llm_result.answer
        report["summary"] = llm_result.answer
        report["risk_summary"] = llm_result.risk_summary
        report_tools.append("openai_compatible_chat")
        report_trace_data["llm"] = {**llm_result.trace_data, "risk_summary": llm_result.risk_summary}
        llm_input_tokens = llm_result.input_tokens
        llm_output_tokens = llm_result.output_tokens
    report_prompt = _make_prompt(question, evidence, findings, "report_agent")
    workflow_steps.append(
        WorkflowStep(
            name="report_agent",
            status="completed",
            detail=f"assembled {len(report['findings'])} report items",
            duration_ms=_elapsed_ms(start),
        )
    )
    workflow_trace.append(
        WorkflowTraceEntry(
            name="report_agent",
            status="completed",
            detail=f"assembled {len(report['findings'])} report items",
            duration_ms=workflow_steps[-1].duration_ms,
            prompt=report_prompt,
            tool_calls=report_tools,
            input_tokens=_estimate_tokens(report_prompt) + llm_input_tokens,
            output_tokens=max(1, len(report["findings"]) * 48) + llm_output_tokens,
            failure_reason=report_failure_reason,
            trace_data=report_trace_data,
        )
    )

    return {
        "trace_id": trace_id,
        "answer": answer,
        "citations": [chunk_to_citation(item, rank=index) for index, item in enumerate(evidence, start=1)],
        "retrieval_diagnostics": retrieval_diagnostics,
        "findings": report["findings"],
        "report": report,
        "workflow_steps": [step.__dict__ for step in workflow_steps],
        "workflow_trace": [entry.__dict__ for entry in workflow_trace],
    }


def run_audit_workflow(
    question: str,
    evidence_loader: Callable[[str], list[RetrievedChunk] | tuple[list[RetrievedChunk], dict[str, Any]]],
) -> dict[str, Any]:
    """Run the LangGraph workflow, with a local fallback for minimal dev installs."""
    try:
        from app.services.langgraph_workflow import run_langgraph_workflow
    except ImportError:
        return _run_sequential_workflow(question, evidence_loader)
    return run_langgraph_workflow(question, evidence_loader)


def build_risk_report(
    question: str,
    evidence: Iterable[RetrievedChunk],
    findings: list[AuditFinding],
) -> dict[str, Any]:
    evidence_list = list(evidence)
    evidence_rank_by_chunk_id = {chunk.chunk_id: index for index, chunk in enumerate(evidence_list, start=1)}
    risk_counts = {"high": 0, "medium": 0, "low": 0}
    normalized_findings = []
    for finding in findings:
        bucket = normalize_level(finding.level)
        risk_counts[bucket] += 1
        evidence_sources = [
            {
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "source": chunk.source,
                "location_label": chunk.location_label,
                "evidence_rank": evidence_rank_by_chunk_id.get(chunk.chunk_id),
            }
            for chunk in evidence_list
            if chunk.document_id in finding.evidence_ids
        ]
        normalized_findings.append(
            {
                "level": finding.level,
                "title": finding.title,
                "rationale": finding.rationale,
                "recommendation": finding.recommendation,
                "evidence_ids": finding.evidence_ids,
                "evidence_refs": [
                    f"Evidence {source['evidence_rank']}"
                    for source in evidence_sources
                    if source.get("evidence_rank") is not None
                ],
                "evidence_sources": evidence_sources,
            }
        )

    overall_level = "low"
    if risk_counts["high"]:
        overall_level = "high"
    elif risk_counts["medium"]:
        overall_level = "medium"

    return {
        "question": question,
        "overall_level": overall_level,
        "finding_count": len(findings),
        "risk_counts": risk_counts,
        "summary": grounded_answer(question, evidence_list),
        "findings": normalized_findings,
        "evidence": [chunk_to_citation(chunk, rank=index) for index, chunk in enumerate(evidence_list, start=1)],
    }


def chunk_to_citation(item: RetrievedChunk, rank: int | None = None) -> dict[str, Any]:
    return {
        "document_id": item.document_id,
        "chunk_id": item.chunk_id,
        "title": item.title,
        "source": item.source,
        "location": item.location,
        "location_label": item.location_label,
        "excerpt": item.text,
        "score": item.score,
        "selected_rank": rank,
        "lexical_score": item.lexical_score,
        "semantic_score": item.semantic_score,
        "fusion_score": item.fusion_score,
        "rerank_score": item.rerank_score,
    }


def finding_to_payload(item: AuditFinding) -> dict[str, Any]:
    return {
        "level": item.level,
        "title": item.title,
        "rationale": item.rationale,
        "recommendation": item.recommendation,
        "evidence_ids": item.evidence_ids,
    }


def normalize_level(level: str) -> str:
    value = level.lower()
    if "high" in value or "高" in level:
        return "high"
    if "medium" in value or "中" in level:
        return "medium"
    return "low"


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _retrieval_detail(evidence_count: int, diagnostics: dict[str, Any]) -> str:
    if not diagnostics:
        return f"retrieved {evidence_count} evidence chunks"
    return (
        f"lexical={diagnostics.get('lexical_candidates', 0)}, "
        f"vector={diagnostics.get('semantic_candidates', 0)}, "
        f"fused={diagnostics.get('fused_candidates', 0)}, "
        f"selected={evidence_count}, "
        f"reranker={'applied' if diagnostics.get('reranker_applied') else 'fallback'}"
    )
