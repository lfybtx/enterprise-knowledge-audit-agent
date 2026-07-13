"""LangGraph orchestration for the enterprise knowledge audit workflow."""
from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.services.audit import AuditFinding, assess
from app.services.llm_synthesis import LlmSynthesisError, synthesize_answer
from app.services.retrieval import RetrievedChunk, grounded_answer
from app.services.workflow import (
    WorkflowStep,
    WorkflowTraceEntry,
    _estimate_tokens,
    _make_prompt,
    _retrieval_detail,
    _elapsed_ms,
    build_risk_report,
    chunk_to_citation,
    finding_to_payload,
    normalize_level,
)


class AuditGraphState(TypedDict, total=False):
    question: str
    evidence_loader: Callable[[str], list[RetrievedChunk] | tuple[list[RetrievedChunk], dict[str, Any]]]
    evidence: list[RetrievedChunk]
    retrieval_diagnostics: dict[str, Any]
    findings: list[AuditFinding]
    report: dict[str, Any]
    answer: str
    workflow_steps: list[dict[str, Any]]
    workflow_trace: list[dict[str, Any]]
    approval_status: str


def run_langgraph_workflow(
    question: str,
    evidence_loader: Callable[[str], list[RetrievedChunk] | tuple[list[RetrievedChunk], dict[str, Any]]],
) -> dict[str, Any]:
    graph = _build_graph()
    state = graph.invoke({"question": question, "evidence_loader": evidence_loader, "workflow_steps": [], "workflow_trace": []})
    evidence = state.get("evidence", [])
    findings = state.get("findings", [])
    report = state.get("report", {})
    return {
        "trace_id": _trace_id(),
        "answer": state.get("answer") or grounded_answer(question, evidence),
        "citations": [chunk_to_citation(item, rank=index) for index, item in enumerate(evidence, start=1)],
        "retrieval_diagnostics": state.get("retrieval_diagnostics", {}),
        "findings": report.get("findings", [finding_to_payload(item) for item in findings]),
        "report": report,
        "workflow_steps": state.get("workflow_steps", []),
        "workflow_trace": state.get("workflow_trace", []),
        "approval_status": state.get("approval_status", "not_required"),
        "requires_human_review": state.get("approval_status") == "pending",
    }


def _build_graph():
    graph = StateGraph(AuditGraphState)
    graph.add_node("retrieval_agent", _retrieval_agent)
    graph.add_node("audit_agent", _audit_agent)
    graph.add_node("report_agent", _report_agent)
    graph.add_node("human_review", _human_review)
    graph.add_edge(START, "retrieval_agent")
    graph.add_edge("retrieval_agent", "audit_agent")
    graph.add_edge("audit_agent", "report_agent")
    graph.add_conditional_edges(
        "report_agent",
        _next_after_report,
        {"human_review": "human_review", "complete": END},
    )
    graph.add_edge("human_review", END)
    return graph.compile()


def _retrieval_agent(state: AuditGraphState) -> dict[str, Any]:
    start = perf_counter()
    loaded = state["evidence_loader"](state["question"])
    if isinstance(loaded, tuple):
        evidence, diagnostics = loaded
    else:
        evidence, diagnostics = loaded, {}
    prompt = _make_prompt(state["question"], evidence, [], "retrieval_agent")
    tools = ["evidence_loader"]
    if diagnostics:
        tools = ["keyword_search", "pgvector_search", "fusion"]
        if diagnostics.get("reranker_applied"):
            tools.append("local_reranker")
    detail = _retrieval_detail(len(evidence), diagnostics)
    return _append_trace(
        state,
        WorkflowStep("retrieval_agent", "completed" if evidence else "empty", detail, _elapsed_ms(start)),
        WorkflowTraceEntry(
            "retrieval_agent", "completed" if evidence else "empty", detail, _elapsed_ms(start), prompt, tools,
            _estimate_tokens(prompt), max(1, len(evidence) * 24),
            None if evidence else "No evidence returned by retrieval stage", {"retrieval": diagnostics},
        ),
        evidence=evidence,
        retrieval_diagnostics=diagnostics,
    )


def _audit_agent(state: AuditGraphState) -> dict[str, Any]:
    start = perf_counter()
    findings = assess(state["question"], state.get("evidence", []))
    prompt = _make_prompt(state["question"], state.get("evidence", []), findings, "audit_agent")
    detail = f"generated {len(findings)} findings"
    return _append_trace(
        state,
        WorkflowStep("audit_agent", "completed" if findings else "empty", detail, _elapsed_ms(start)),
        WorkflowTraceEntry(
            "audit_agent", "completed" if findings else "empty", detail, _elapsed_ms(start), prompt, ["assess"],
            _estimate_tokens(prompt), max(1, len(findings) * 36), None if findings else "No findings were produced",
        ),
        findings=findings,
    )


def _report_agent(state: AuditGraphState) -> dict[str, Any]:
    start = perf_counter()
    report = build_risk_report(state["question"], state.get("evidence", []), state.get("findings", []))
    answer = grounded_answer(state["question"], state.get("evidence", []))
    tools = ["build_risk_report"]
    trace_data: dict[str, Any] = {}
    failure_reason = None
    llm_input_tokens = 0
    llm_output_tokens = 0
    try:
        llm_result = synthesize_answer(
            question=state["question"],
            evidence=state.get("evidence", []),
            findings=state.get("findings", []),
        )
    except LlmSynthesisError as error:
        llm_result = None
        failure_reason = str(error)
        trace_data["llm"] = {"status": "fallback", "failure_reason": str(error)}
    if llm_result is not None:
        answer = llm_result.answer
        report["summary"] = llm_result.answer
        tools.append("openai_compatible_chat")
        trace_data["llm"] = llm_result.trace_data
        llm_input_tokens = llm_result.input_tokens
        llm_output_tokens = llm_result.output_tokens
    prompt = _make_prompt(state["question"], state.get("evidence", []), state.get("findings", []), "report_agent")
    detail = f"assembled {len(report['findings'])} report items"
    return _append_trace(
        state,
        WorkflowStep("report_agent", "completed", detail, _elapsed_ms(start)),
        WorkflowTraceEntry(
            "report_agent", "completed", detail, _elapsed_ms(start), prompt, tools,
            _estimate_tokens(prompt) + llm_input_tokens, max(1, len(report["findings"]) * 48) + llm_output_tokens,
            failure_reason, trace_data,
        ),
        report=report,
        answer=answer,
    )


def _next_after_report(state: AuditGraphState) -> str:
    return "human_review" if state.get("evidence") and state.get("findings") else "complete"


def _human_review(state: AuditGraphState) -> dict[str, Any]:
    start = perf_counter()
    prompt = "Human confirmation is required before the high-risk audit result can be actioned."
    return _append_trace(
        state,
        WorkflowStep("human_review", "pending", "high-risk or conflicting findings require human confirmation", _elapsed_ms(start)),
        WorkflowTraceEntry(
            "human_review", "pending", "high-risk or conflicting findings require human confirmation", _elapsed_ms(start),
            prompt, ["human_confirmation"], _estimate_tokens(prompt), 0, None,
        ),
        approval_status="pending",
    )


def _append_trace(state: AuditGraphState, step: WorkflowStep, trace: WorkflowTraceEntry, **updates: Any) -> dict[str, Any]:
    return {
        "workflow_steps": [*state.get("workflow_steps", []), step.__dict__],
        "workflow_trace": [*state.get("workflow_trace", []), trace.__dict__],
        **updates,
    }


def _trace_id() -> str:
    from uuid import uuid4

    return str(uuid4())
