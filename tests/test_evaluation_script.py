from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.run_evaluation import run_evaluation


def test_run_evaluation_writes_summary_file(tmp_path):
    output_path = tmp_path / "evaluation_results.json"
    report_path = tmp_path / "evaluation-report.md"
    html_report_path = tmp_path / "evaluation-report.html"

    payload = run_evaluation(Path("data/evaluation_cases.json"), output_path)
    from scripts.run_evaluation import render_html_report, render_markdown_report
    report_path.write_text(
        render_markdown_report(payload, output_path, Path("data/evaluation_cases.json")),
        encoding="utf-8",
    )
    html_report_path.write_text(
        render_html_report(payload, output_path, Path("data/evaluation_cases.json")),
        encoding="utf-8",
    )

    assert output_path.exists()
    assert report_path.exists()
    assert html_report_path.exists()
    assert payload["summary"]["total"] >= 100
    assert payload["summary"]["negative_cases"] > 0
    assert 0 <= payload["summary"]["recall_at_1"] <= 1
    assert 0 <= payload["summary"]["citation_accuracy"] <= 1
    assert 0 <= payload["summary"]["risk_type_accuracy"] <= 1
    assert 0 <= payload["summary"]["conflict_accuracy"] <= 1
    assert 0 <= payload["summary"]["evidence_binding_accuracy"] <= 1
    assert 0 <= payload["summary"]["review_trigger_accuracy"] <= 1
    assert 0 <= payload["summary"]["refusal_accuracy"] <= 1
    assert 0 <= payload["summary"]["judge_pass_rate"] <= 1
    assert {"keyword_only", "vector_only", "hybrid", "hybrid_rerank"} <= set(payload["comparison"])
    assert len(payload["metric_table"]) == 4
    assert "failure_breakdown" in payload
    assert payload["failure_breakdown"]["refusal"] >= 0
    assert payload["judge"]["deepseek_supported"] is True
    assert payload["summary"]["average_latency_ms"] >= 0
    assert payload["outcomes"][0]["actual_document_ids"]
    assert any(item["expected_refusal"] for item in payload["outcomes"])
    report_text = report_path.read_text(encoding="utf-8")
    assert "Recall@1" in report_text
    assert "Retrieval Strategy Comparison" in report_text
    html_text = html_report_path.read_text(encoding="utf-8")
    assert "<table>" in html_text


def test_evaluation_results_endpoint_returns_baseline_summary():
    client = TestClient(app)

    response = client.get("/api/evaluation-results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] >= 100
    assert "recall_at_1" in payload["summary"]
    assert "risk_type_accuracy" in payload["summary"]
    assert "metric_table" in payload
