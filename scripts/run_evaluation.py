from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.retrieval import HybridRetriever, grounded_answer  # noqa: E402


DEFAULT_CASES_PATH = ROOT / "data" / "evaluation_cases.json"
DEFAULT_RESULTS_PATH = ROOT / "data" / "evaluation_results.json"
DEFAULT_REPORT_PATH = ROOT / "docs" / "evaluation-report.md"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def evaluate_case(retriever: HybridRetriever, case: dict[str, Any]) -> dict[str, Any]:
    results = retriever.search(case["question"], limit=3)
    top = results[0] if results else None
    expected_document_id = case["expected_document_id"]
    expected_location_kind = case.get("expected_location_kind")
    actual_document_ids = [item.document_id for item in results]
    answer = grounded_answer(case["question"], results)
    citation_marker_present = "[证据" in answer or "[璇佹嵁" in answer

    return {
        "id": case["id"],
        "question": case["question"],
        "expected_document_id": expected_document_id,
        "actual_document_ids": actual_document_ids,
        "top_document_id": top.document_id if top else None,
        "top_location_kind": top.location.get("kind") if top else None,
        "recall_at_1": bool(top and top.document_id == expected_document_id),
        "recall_at_3": expected_document_id in actual_document_ids,
        "citation_correct": bool(
            top
            and top.document_id == expected_document_id
            and (expected_location_kind is None or top.location.get("kind") == expected_location_kind)
        ),
        "answer_quality_passed": bool(results and citation_marker_present and "No searchable evidence" not in answer),
    }


def summarize(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(outcomes)
    if not total:
        return {
            "total": 0,
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "citation_accuracy": 0.0,
            "answer_quality_rate": 0.0,
        }

    def rate(key: str) -> float:
        return round(sum(1 for item in outcomes if item[key]) / total, 4)

    return {
        "total": total,
        "recall_at_1": rate("recall_at_1"),
        "recall_at_3": rate("recall_at_3"),
        "citation_accuracy": rate("citation_correct"),
        "answer_quality_rate": rate("answer_quality_passed"),
    }


def run_evaluation(cases_path: Path, results_path: Path) -> dict[str, Any]:
    documents = load_json(ROOT / "app" / "data" / "sample_documents.json")
    cases = load_json(cases_path)
    retriever = HybridRetriever(documents)
    outcomes = [evaluate_case(retriever, case) for case in cases]
    summary = summarize(outcomes)
    payload = {"summary": summary, "outcomes": outcomes}
    write_json(results_path, payload)
    return payload


def print_report(payload: dict[str, Any], results_path: Path) -> None:
    summary = payload["summary"]
    print("Evaluation summary")
    print(f"- Total cases: {summary['total']}")
    print(f"- Recall@1: {summary['recall_at_1']:.1%}")
    print(f"- Recall@3: {summary['recall_at_3']:.1%}")
    print(f"- Citation accuracy: {summary['citation_accuracy']:.1%}")
    print(f"- Answer quality pass rate: {summary['answer_quality_rate']:.1%}")
    print(f"- Results file: {results_path}")

    failures = [item for item in payload["outcomes"] if not item["recall_at_1"]]
    if failures:
        print("\nTop Recall@1 failures:")
        for item in failures[:10]:
            print(
                f"- {item['id']}: expected={item['expected_document_id']} "
                f"actual={item['top_document_id']} question={item['question']}"
            )


def render_markdown_report(payload: dict[str, Any], results_path: Path, cases_path: Path) -> str:
    summary = payload["summary"]
    failures = [item for item in payload["outcomes"] if not item["recall_at_1"]]
    display_results_path = results_path.resolve().relative_to(ROOT) if results_path.resolve().is_relative_to(ROOT) else results_path
    display_cases_path = cases_path.resolve().relative_to(ROOT) if cases_path.resolve().is_relative_to(ROOT) else cases_path
    lines = [
        "# Evaluation Report",
        "",
        f"- Cases file: `{display_cases_path.as_posix()}`",
        f"- Results file: `{display_results_path.as_posix()}`",
        f"- Total cases: {summary['total']}",
        f"- Recall@1: {summary['recall_at_1']:.1%}",
        f"- Recall@3: {summary['recall_at_3']:.1%}",
        f"- Citation accuracy: {summary['citation_accuracy']:.1%}",
        f"- Answer quality pass rate: {summary['answer_quality_rate']:.1%}",
        "",
        "## Top Recall@1 failures",
    ]
    if failures:
        for item in failures[:10]:
            lines.append(
                f"- `{item['id']}` expected `{item['expected_document_id']}` "
                f"but retrieved `{item['top_document_id']}`"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Method",
            "- `Recall@1` checks whether the top result matches the expected document.",
            "- `Recall@3` checks whether the expected document appears in the top three results.",
            "- `Citation accuracy` checks whether the top result also matches the expected location kind.",
            "- `Answer quality` checks whether the grounded answer contains evidence markers and does not fall back to the no-evidence path.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval, citation, and answer-quality evaluation.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    payload = run_evaluation(args.cases, args.output)
    print_report(payload, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_markdown_report(payload, args.output, args.cases), encoding="utf-8")
    print(f"- Markdown report: {args.report}")


if __name__ == "__main__":
    main()
