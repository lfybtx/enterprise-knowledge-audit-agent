# Evaluation Report

- Cases file: `data/evaluation_cases.json`
- Results file: `data/evaluation_results.json`
- Total cases: 50
- Recall@1: 98.0%
- Recall@3: 100.0%
- Citation accuracy: 98.0%
- Answer quality pass rate: 100.0%

## Top Recall@1 failures
- `legacy-export-008` expected `legacy-export-guide` but retrieved `sales-export-v2`

## Method
- `Recall@1` checks whether the top result matches the expected document.
- `Recall@3` checks whether the expected document appears in the top three results.
- `Citation accuracy` checks whether the top result also matches the expected location kind.
- `Answer quality` checks whether the grounded answer contains evidence markers and does not fall back to the no-evidence path.
