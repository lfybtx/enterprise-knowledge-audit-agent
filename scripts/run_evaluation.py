from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.audit import AuditFinding, assess  # noqa: E402
from app.services.reranking import rerank_candidates  # noqa: E402
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


def evaluate_case(results: list[Any], case: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    top = results[0] if results else None
    expected_document_id = case["expected_document_id"]
    expected_location_kind = case.get("expected_location_kind")
    actual_document_ids = [item.document_id for item in results]
    answer = grounded_answer(case["question"], results)
    citation_marker_present = "[证据" in answer or "[Evidence" in answer
    findings = assess(case["question"], results) if results else []
    detected_risk_types = sorted(_risk_types_from_findings(findings))
    expected_risk_types = sorted(case.get("expected_risk_types", []))
    expected_conflict = case.get("expected_conflict")
    expected_review_required = case.get("expected_review_required")
    expected_evidence_document_ids = case.get("expected_evidence_document_ids")
    bound_evidence_ids = {evidence_id for finding in findings for evidence_id in finding.evidence_ids}
    conflict_present = any(_finding_has_risk_type(finding, "conflict") for finding in findings)
    high_risk_present = any(_normalize_level(finding.level) == "high" for finding in findings)

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
        "expected_risk_types": expected_risk_types,
        "detected_risk_types": detected_risk_types,
        "risk_type_correct": _optional_metric(
            expected_risk_types,
            all(risk_type in detected_risk_types for risk_type in expected_risk_types),
        ),
        "expected_conflict": expected_conflict,
        "conflict_detected": conflict_present,
        "conflict_correct": _optional_metric("expected" if expected_conflict is True else None, conflict_present is True),
        "expected_review_required": expected_review_required,
        "review_required_detected": high_risk_present,
        "review_trigger_correct": _optional_metric(
            "expected" if expected_review_required is True else None,
            high_risk_present is True,
        ),
        "expected_evidence_document_ids": expected_evidence_document_ids or [],
        "bound_evidence_document_ids": sorted(bound_evidence_ids),
        "evidence_binding_correct": _optional_metric(
            expected_evidence_document_ids,
            bool(expected_evidence_document_ids)
            and all(document_id in bound_evidence_ids for document_id in expected_evidence_document_ids),
        ),
        "latency_ms": round(latency_ms, 2),
        "failed": not bool(results),
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
            "average_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "failure_rate": 0.0,
            "risk_type_accuracy": 0.0,
            "conflict_accuracy": 0.0,
            "evidence_binding_accuracy": 0.0,
            "review_trigger_accuracy": 0.0,
        }

    def rate(key: str) -> float:
        return round(sum(1 for item in outcomes if item[key]) / total, 4)

    latencies = sorted(item["latency_ms"] for item in outcomes)
    p95_index = min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))
    return {
        "total": total,
        "recall_at_1": rate("recall_at_1"),
        "recall_at_3": rate("recall_at_3"),
        "citation_accuracy": rate("citation_correct"),
        "answer_quality_rate": rate("answer_quality_passed"),
        "average_latency_ms": round(sum(latencies) / total, 2),
        "p95_latency_ms": latencies[p95_index],
        "failure_rate": rate("failed"),
        "risk_type_accuracy": optional_rate(outcomes, "risk_type_correct"),
        "conflict_accuracy": optional_rate(outcomes, "conflict_correct"),
        "evidence_binding_accuracy": optional_rate(outcomes, "evidence_binding_correct"),
        "review_trigger_accuracy": optional_rate(outcomes, "review_trigger_correct"),
    }


def optional_rate(outcomes: list[dict[str, Any]], key: str) -> float:
    evaluated = [item for item in outcomes if item.get(key) is not None]
    if not evaluated:
        return 0.0
    return round(sum(1 for item in evaluated if item[key]) / len(evaluated), 4)


def _optional_metric(expected: Any, passed: bool) -> bool | None:
    if expected is None or expected == []:
        return None
    return bool(passed)


def _risk_types_from_findings(findings: list[AuditFinding]) -> set[str]:
    risk_types: set[str] = set()
    for finding in findings:
        for risk_type in ["data_export", "permission", "contract_sla", "sensitive_data", "approval_missing", "conflict"]:
            if _finding_has_risk_type(finding, risk_type):
                risk_types.add(risk_type)
    return risk_types


def _finding_has_risk_type(finding: AuditFinding, risk_type: str) -> bool:
    text = f"{finding.title} {finding.rationale} {finding.recommendation}".lower()
    if risk_type == "data_export":
        return any(term in text for term in ["导出", "export", "customer data"])
    if risk_type == "permission":
        return any(term in text for term in ["权限", "permission", "role", "access", "shared account"])
    if risk_type == "contract_sla":
        return any(term in text for term in ["合同", "sla", "服务承诺", "法务", "legal", "compensation"])
    if risk_type == "sensitive_data":
        return any(term in text for term in ["敏感", "泄露", "personal", "secret", "token", "log", "leak"])
    if risk_type == "approval_missing":
        return any(term in text for term in ["缺少审批", "证据不足", "no approval", "without approval", "approval"])
    if risk_type == "conflict":
        return any(term in text for term in ["冲突", "conflict", "不一致"])
    return False


def _normalize_level(level: str) -> str:
    value = level.lower()
    if "high" in value or "高" in level:
        return "high"
    if "medium" in value or "中" in level:
        return "medium"
    return "low"


def _evaluate_pipeline(cases: list[dict[str, Any]], search: Any) -> list[dict[str, Any]]:
    outcomes = []
    for case in cases:
        start = perf_counter()
        try:
            results = search(case["question"])
        except Exception:
            results = []
        outcomes.append(evaluate_case(results, case, (perf_counter() - start) * 1000))
    return outcomes


def run_evaluation(cases_path: Path, results_path: Path) -> dict[str, Any]:
    documents = load_json(ROOT / "app" / "data" / "sample_documents.json")
    cases = load_json(cases_path)
    retriever = HybridRetriever(documents)
    fusion_outcomes = _evaluate_pipeline(cases, lambda question: retriever.search(question, limit=20)[:3])
    reranked_outcomes = _evaluate_pipeline(
        cases,
        lambda question: rerank_candidates(question, retriever.search(question, limit=20))[:3],
    )
    summary = summarize(reranked_outcomes)
    payload = {
        "summary": summary,
        "outcomes": reranked_outcomes,
        "comparison": {
            "fusion_baseline": summarize(fusion_outcomes),
            "reranked": summary,
        },
        "failure_breakdown": failure_breakdown(reranked_outcomes),
    }
    write_json(results_path, payload)
    return payload


def failure_breakdown(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "retrieval": sum(1 for item in outcomes if not item["recall_at_1"]),
        "citation": sum(1 for item in outcomes if not item["citation_correct"]),
        "risk_type": sum(1 for item in outcomes if item.get("risk_type_correct") is False),
        "conflict": sum(1 for item in outcomes if item.get("conflict_correct") is False),
        "evidence_binding": sum(1 for item in outcomes if item.get("evidence_binding_correct") is False),
        "review_trigger": sum(1 for item in outcomes if item.get("review_trigger_correct") is False),
    }


def print_report(payload: dict[str, Any], results_path: Path) -> None:
    summary = payload["summary"]
    print("Evaluation summary")
    print(f"- Total cases: {summary['total']}")
    print(f"- Recall@1: {summary['recall_at_1']:.1%}")
    print(f"- Recall@3: {summary['recall_at_3']:.1%}")
    print(f"- Citation accuracy: {summary['citation_accuracy']:.1%}")
    print(f"- Answer quality pass rate: {summary['answer_quality_rate']:.1%}")
    print(f"- Risk type accuracy: {summary['risk_type_accuracy']:.1%}")
    print(f"- Conflict accuracy: {summary['conflict_accuracy']:.1%}")
    print(f"- Evidence binding accuracy: {summary['evidence_binding_accuracy']:.1%}")
    print(f"- Review trigger accuracy: {summary['review_trigger_accuracy']:.1%}")
    print(f"- Average latency: {summary['average_latency_ms']:.2f} ms")
    print(f"- P95 latency: {summary['p95_latency_ms']:.2f} ms")
    print(f"- Failure rate: {summary['failure_rate']:.1%}")
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
    comparison = payload.get("comparison", {})
    breakdown = payload.get("failure_breakdown", {})
    failures = [
        item
        for item in payload["outcomes"]
        if not item["recall_at_1"]
        or item.get("risk_type_correct") is False
        or item.get("conflict_correct") is False
        or item.get("evidence_binding_correct") is False
        or item.get("review_trigger_correct") is False
    ]
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
        f"- Risk type accuracy: {summary['risk_type_accuracy']:.1%}",
        f"- Conflict accuracy: {summary['conflict_accuracy']:.1%}",
        f"- Evidence binding accuracy: {summary['evidence_binding_accuracy']:.1%}",
        f"- Review trigger accuracy: {summary['review_trigger_accuracy']:.1%}",
        f"- Average latency: {summary['average_latency_ms']:.2f} ms",
        f"- P95 latency: {summary['p95_latency_ms']:.2f} ms",
        f"- Failure rate: {summary['failure_rate']:.1%}",
        "",
        "## Fusion And Reranker Comparison",
        "",
        "| Pipeline | Recall@1 | Recall@3 | Citation accuracy | Risk accuracy | Conflict accuracy | Avg latency | Failure rate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, result in comparison.items():
        lines.append(
            f"| {name} | {result['recall_at_1']:.1%} | {result['recall_at_3']:.1%} | "
            f"{result['citation_accuracy']:.1%} | {result['risk_type_accuracy']:.1%} | "
            f"{result['conflict_accuracy']:.1%} | {result['average_latency_ms']:.2f} ms | "
            f"{result['failure_rate']:.1%} |"
        )
    lines.extend(["", "## Failure Breakdown", ""])
    for key in ["retrieval", "citation", "risk_type", "conflict", "evidence_binding", "review_trigger"]:
        lines.append(f"- {key}: {breakdown.get(key, 0)}")
    lines.extend(["", "## Top Evaluation Failures", ""])
    if failures:
        for item in failures[:10]:
            lines.append(
                f"- `{item['id']}` expected doc `{item['expected_document_id']}`, top doc `{item['top_document_id']}`, "
                f"expected risks `{item.get('expected_risk_types', [])}`, detected risks `{item.get('detected_risk_types', [])}`"
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
            "- `Risk type accuracy` checks whether expected audit risk types were detected from retrieved evidence.",
            "- `Conflict accuracy` checks whether conflict-labelled cases produced conflict findings.",
            "- `Evidence binding accuracy` checks whether findings cite the expected source documents.",
            "- `Review trigger accuracy` checks whether high-risk cases would require human review.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval, citation, answer-quality, and audit-risk evaluation.")
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
