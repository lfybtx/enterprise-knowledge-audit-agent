# Evaluation Report

- Cases file: `data/evaluation_cases.json`
- Results file: `data/evaluation_results.json`
- Total cases: 122 (110 positive, 12 negative)
- Recall@1: 98.2%
- Recall@3: 100.0%
- Citation accuracy: 98.2%
- Answer quality pass rate: 100.0%
- Refusal accuracy: 100.0%
- Judge pass rate: 98.4%
- Average latency: 0.98 ms
- P95 latency: 1.51 ms
- Failure rate: 0.0%

## Retrieval Strategy Comparison

| Strategy | Recall@1 | Recall@3 | Citation | Answer quality | Refusal | Judge pass | Avg latency | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| keyword_only | 98.2% | 100.0% | 98.2% | 100.0% | 100.0% | 98.4% | 0.15 ms | 0.0% |
| vector_only | 90.9% | 100.0% | 90.9% | 100.0% | 100.0% | 91.8% | 0.16 ms | 0.0% |
| hybrid | 98.2% | 100.0% | 98.2% | 100.0% | 100.0% | 98.4% | 0.15 ms | 0.0% |
| hybrid_rerank | 98.2% | 100.0% | 98.2% | 100.0% | 100.0% | 98.4% | 0.98 ms | 0.0% |

## Failure Breakdown

- retrieval: 2
- citation: 2
- risk_type: 1
- conflict: 1
- evidence_binding: 0
- review_trigger: 0
- refusal: 0

## Method
- Positive cases are evaluated for Recall@1, Recall@3, citation accuracy, answer quality, risk type, conflict, evidence binding, and review trigger behavior.
- Negative cases are unsafe or unsupported requests; the expected behavior is refusal.
- `keyword_only`, `vector_only`, `hybrid`, and `hybrid_rerank` are run against the same expanded case set.
- LLM-as-judge defaults to a deterministic local judge. Set `EVALUATION_JUDGE_PROVIDER=deepseek` with `DEEPSEEK_API_KEY` to use DeepSeek-compatible scoring.
