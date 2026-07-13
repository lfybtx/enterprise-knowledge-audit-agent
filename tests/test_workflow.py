from app.services.retrieval import RetrievedChunk
from app.services.workflow import build_risk_report, run_audit_workflow


def test_run_audit_workflow_returns_structured_report():
    evidence = [
        RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            title="Export policy",
            source="policy.txt",
            text="Manager approval is required before exporting customer data.",
            location={"kind": "document"},
            score=0.91,
        )
    ]

    response = run_audit_workflow("Customer export approval", lambda _: evidence)

    assert response["citations"][0]["chunk_id"] == "chunk-1"
    assert response["citations"][0]["selected_rank"] == 1
    assert response["workflow_steps"][0]["name"] == "retrieval_agent"
    assert response["workflow_trace"][0]["tool_calls"] == ["evidence_loader"]
    assert response["workflow_trace"][0]["prompt"].startswith("Question:")
    assert response["workflow_trace"][0]["input_tokens"] >= 1
    assert "report" in response
    assert response["report"]["evidence"][0]["document_id"] == "doc-1"
    assert response["trace_id"]


def test_workflow_records_retrieval_diagnostics_in_trace():
    evidence = [
        RetrievedChunk(
            chunk_id="chunk-1", document_id="doc-1", title="Export policy", source="policy.txt",
            text="Manager approval is required.", location={"kind": "document"}, score=0.9,
            lexical_score=0.8, semantic_score=0.7, fusion_score=0.75, rerank_score=1.2,
        )
    ]
    response = run_audit_workflow(
        "Customer export approval",
        lambda _: (evidence, {"lexical_candidates": 20, "semantic_candidates": 20, "fused_candidates": 25, "reranker_applied": True}),
    )

    assert "lexical=20" in response["workflow_trace"][0]["detail"]
    assert "local_reranker" in response["workflow_trace"][0]["tool_calls"]
    assert response["citations"][0]["rerank_score"] == 1.2
    assert response["workflow_trace"][0]["trace_data"]["retrieval"]["lexical_candidates"] == 20


def test_build_risk_report_counts_findings_by_level():
    evidence = [
        RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            title="Export policy",
            source="policy.txt",
            text="Manager approval is required before exporting customer data.",
            location={"kind": "document"},
            score=0.91,
        )
    ]
    findings = [
        type(
            "Finding",
            (),
            {
                "level": "High",
                "title": "Export risk",
                "rationale": "Approval missing",
                "recommendation": "Require approval",
                "evidence_ids": ["doc-1"],
            },
        )()
    ]

    report = build_risk_report("Customer export approval", evidence, findings)

    assert report["overall_level"] == "high"
    assert report["risk_counts"]["high"] == 1


def test_run_audit_workflow_records_empty_retrieval_trace():
    response = run_audit_workflow("No evidence question", lambda _: [])

    assert response["workflow_trace"][0]["status"] == "empty"
    assert response["workflow_trace"][0]["failure_reason"] == "No evidence returned by retrieval stage"
