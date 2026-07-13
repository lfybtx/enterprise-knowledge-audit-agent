# Evaluation Report

- Cases file: `data/evaluation_cases.json`
- Results file: `data/evaluation_results.json`
- Total cases: 60
- Recall@1: 96.7%
- Recall@3: 100.0%
- Citation accuracy: 96.7%
- Answer quality pass rate: 100.0%
- Risk type accuracy: 90.0%
- Conflict accuracy: 100.0%
- Evidence binding accuracy: 100.0%
- Review trigger accuracy: 100.0%
- Average latency: 1.22 ms
- P95 latency: 1.58 ms
- Failure rate: 0.0%

## Fusion And Reranker Comparison

| Pipeline | Recall@1 | Recall@3 | Citation accuracy | Risk accuracy | Conflict accuracy | Avg latency | Failure rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fusion_baseline | 96.7% | 100.0% | 96.7% | 90.0% | 100.0% | 0.19 ms | 0.0% |
| reranked | 96.7% | 100.0% | 96.7% | 90.0% | 100.0% | 1.22 ms | 0.0% |

## Failure Breakdown

- retrieval: 2
- citation: 2
- risk_type: 1
- conflict: 0
- evidence_binding: 0
- review_trigger: 0

## Top Evaluation Failures

- `risk-export-001` expected doc `eval-current-export-policy`, top doc `eval-legacy-export-guide`, expected risks `['data_export']`, detected risks `['approval_missing', 'conflict', 'contract_sla', 'data_export', 'permission', 'sensitive_data']`
- `risk-retention-conflict-001` expected doc `eval-current-export-policy`, top doc `eval-legacy-export-guide`, expected risks `['data_export']`, detected risks `['approval_missing', 'conflict', 'contract_sla', 'data_export', 'permission', 'sensitive_data']`
- `risk-cross-share-001` expected doc `eval-access-control-policy`, top doc `eval-access-control-policy`, expected risks `['approval_missing', 'permission']`, detected risks `['contract_sla', 'data_export', 'permission', 'sensitive_data']`

## Method
- `Recall@1` checks whether the top result matches the expected document.
- `Recall@3` checks whether the expected document appears in the top three results.
- `Citation accuracy` checks whether the top result also matches the expected location kind.
- `Answer quality` checks whether the grounded answer contains evidence markers and does not fall back to the no-evidence path.
- `Risk type accuracy` checks whether expected audit risk types were detected from retrieved evidence.
- `Conflict accuracy` checks whether conflict-labelled cases produced conflict findings.
- `Evidence binding accuracy` checks whether findings cite the expected source documents.
- `Review trigger accuracy` checks whether high-risk cases would require human review.
