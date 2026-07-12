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
    assert response["workflow_steps"][0]["name"] == "retrieval_agent"
    assert response["workflow_trace"][0]["tool_calls"] == ["evidence_loader"]
    assert response["workflow_trace"][0]["prompt"].startswith("Question:")
    assert response["workflow_trace"][0]["input_tokens"] >= 1
    assert "report" in response
    assert response["report"]["evidence"][0]["document_id"] == "doc-1"
    assert response["trace_id"]


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
