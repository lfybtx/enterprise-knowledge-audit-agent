from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.run_evaluation import run_evaluation


def test_run_evaluation_writes_summary_file(tmp_path):
    output_path = tmp_path / "evaluation_results.json"
    report_path = tmp_path / "evaluation-report.md"

    payload = run_evaluation(Path("data/evaluation_cases.json"), output_path)
    from scripts.run_evaluation import render_markdown_report
    report_path.write_text(
        render_markdown_report(payload, output_path, Path("data/evaluation_cases.json")),
        encoding="utf-8",
    )

    assert output_path.exists()
    assert report_path.exists()
    assert payload["summary"]["total"] == 60
    assert 0 <= payload["summary"]["recall_at_1"] <= 1
    assert 0 <= payload["summary"]["citation_accuracy"] <= 1
    assert 0 <= payload["summary"]["risk_type_accuracy"] <= 1
    assert 0 <= payload["summary"]["conflict_accuracy"] <= 1
    assert 0 <= payload["summary"]["evidence_binding_accuracy"] <= 1
    assert 0 <= payload["summary"]["review_trigger_accuracy"] <= 1
    assert "fusion_baseline" in payload["comparison"]
    assert "reranked" in payload["comparison"]
    assert "failure_breakdown" in payload
    assert payload["summary"]["average_latency_ms"] >= 0
    assert payload["outcomes"][0]["actual_document_ids"]
    report_text = report_path.read_text(encoding="utf-8")
    assert "Recall@1" in report_text
    assert "Risk type accuracy" in report_text


def test_evaluation_results_endpoint_returns_baseline_summary():
    client = TestClient(app)

    response = client.get("/api/evaluation-results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 60
    assert "recall_at_1" in payload["summary"]
    assert "risk_type_accuracy" in payload["summary"]
