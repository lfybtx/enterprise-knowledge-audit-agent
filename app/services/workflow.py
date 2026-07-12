from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from time import perf_counter
from typing import Any, Callable, Iterable

from app.services.audit import AuditFinding, assess
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


def run_audit_workflow(
    question: str,
    evidence_loader: Callable[[str], list[RetrievedChunk]],
) -> dict[str, Any]:
    workflow_steps: list[WorkflowStep] = []
    workflow_trace: list[WorkflowTraceEntry] = []
    trace_id = str(uuid4())

    start = perf_counter()
    evidence = evidence_loader(question)
    retrieval_prompt = _make_prompt(question, evidence, [], "retrieval_agent")
    workflow_steps.append(
        WorkflowStep(
            name="retrieval_agent",
            status="completed" if evidence else "empty",
            detail=f"retrieved {len(evidence)} evidence chunks",
            duration_ms=_elapsed_ms(start),
        )
    )
    workflow_trace.append(
        WorkflowTraceEntry(
            name="retrieval_agent",
            status="completed" if evidence else "empty",
            detail=f"retrieved {len(evidence)} evidence chunks",
            duration_ms=workflow_steps[-1].duration_ms,
            prompt=retrieval_prompt,
            tool_calls=["evidence_loader"],
            input_tokens=_estimate_tokens(retrieval_prompt),
            output_tokens=max(1, len(evidence) * 24),
            failure_reason=None if evidence else "No evidence returned by retrieval stage",
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
            tool_calls=["build_risk_report"],
            input_tokens=_estimate_tokens(report_prompt),
            output_tokens=max(1, len(report["findings"]) * 48),
            failure_reason=None,
        )
    )

    return {
        "trace_id": trace_id,
        "answer": grounded_answer(question, evidence),
        "citations": [chunk_to_citation(item) for item in evidence],
        "findings": [finding_to_payload(item) for item in findings],
        "report": report,
        "workflow_steps": [step.__dict__ for step in workflow_steps],
        "workflow_trace": [entry.__dict__ for entry in workflow_trace],
    }


def build_risk_report(
    question: str,
    evidence: Iterable[RetrievedChunk],
    findings: list[AuditFinding],
) -> dict[str, Any]:
    evidence_list = list(evidence)
    risk_counts = {"high": 0, "medium": 0, "low": 0}
    normalized_findings = []
    for finding in findings:
        bucket = normalize_level(finding.level)
        risk_counts[bucket] += 1
        normalized_findings.append(
            {
                "level": finding.level,
                "title": finding.title,
                "rationale": finding.rationale,
                "recommendation": finding.recommendation,
                "evidence_ids": finding.evidence_ids,
                "evidence_sources": [
                    {
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "title": chunk.title,
                        "source": chunk.source,
                        "location_label": chunk.location_label,
                    }
                    for chunk in evidence_list
                    if chunk.document_id in finding.evidence_ids
                ],
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
        "evidence": [chunk_to_citation(chunk) for chunk in evidence_list],
    }


def chunk_to_citation(item: RetrievedChunk) -> dict[str, Any]:
    return {
        "document_id": item.document_id,
        "chunk_id": item.chunk_id,
        "title": item.title,
        "source": item.source,
        "location": item.location,
        "location_label": item.location_label,
        "excerpt": item.text,
        "score": item.score,
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
