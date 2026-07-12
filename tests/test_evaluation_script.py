from pathlib import Path

from scripts.run_evaluation import run_evaluation


def test_run_evaluation_writes_summary_file(tmp_path):
    output_path = tmp_path / "evaluation_results.json"

    payload = run_evaluation(Path("data/evaluation_cases.json"), output_path)

    assert output_path.exists()
    assert payload["summary"]["total"] == 50
    assert 0 <= payload["summary"]["recall_at_1"] <= 1
    assert 0 <= payload["summary"]["citation_accuracy"] <= 1
    assert payload["outcomes"][0]["actual_document_ids"]
