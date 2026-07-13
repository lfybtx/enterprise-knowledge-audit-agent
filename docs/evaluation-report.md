# Evaluation Report

- Cases file: `data/evaluation_cases.json`
- Results file: `data/evaluation_results.json`
- Total cases: 50
- Recall@1: 100.0%
- Recall@3: 100.0%
- Citation accuracy: 100.0%
- Answer quality pass rate: 100.0%
- Average latency: 485.10 ms
- P95 latency: 308.66 ms
- Failure rate: 0.0%

## Fusion And Reranker Comparison

| Pipeline | Recall@1 | Recall@3 | Citation accuracy | Avg latency | P95 latency | Failure rate |
| --- | --- | --- | --- | --- | --- | --- |
| fusion_baseline | 98.0% | 100.0% | 98.0% | 0.08 ms | 0.15 ms | 0.0% |
| reranked | 100.0% | 100.0% | 100.0% | 485.10 ms | 308.66 ms | 0.0% |

## Top Recall@1 failures
- None

## Method
- `Recall@1` checks whether the top result matches the expected document.
- `Recall@3` checks whether the expected document appears in the top three results.
- `Citation accuracy` checks whether the top result also matches the expected location kind.
- `Answer quality` checks whether the grounded answer contains evidence markers and does not fall back to the no-evidence path.
- The comparison uses the same top-20 fusion candidates, with the reranked pipeline applying the local cross-encoder before selecting top three.
