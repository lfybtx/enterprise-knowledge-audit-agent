import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.retrieval import HybridRetriever  # noqa: E402


def load_json(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def main():
    documents = load_json(ROOT / "app" / "data" / "sample_documents.json")
    cases = load_json(ROOT / "data" / "evaluation_cases.json")
    retriever = HybridRetriever(documents)
    passed = 0

    for case in cases:
        actual = retriever.search(case["question"], limit=1)[0].document_id
        success = actual == case["expected_document_id"]
        passed += success
        print(f"{'PASS' if success else 'FAIL'} | {case['question']} | expected={case['expected_document_id']} actual={actual}")

    print(f"\nRecall@1: {passed / len(cases):.1%} ({passed}/{len(cases)})")


if __name__ == "__main__":
    main()
