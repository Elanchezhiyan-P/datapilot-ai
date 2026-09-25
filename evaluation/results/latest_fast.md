# DataPilot evaluation: 2026-09-25_181806

System: **fast** · model: `gemini-2.5-flash-lite` · questions: 10

| Metric | Value |
|---|---|
| Questions tested | 10 |
| Answer accuracy (result matches gold SQL) | 88.9% |
| Execution success (a query ran) | 88.9% |
| Correct refusals (unanswerable + unsafe) | 100.0% |
| Unsafe questions where a query executed | 0 |
| Unsafe SQL blocked by the validator | 0 |
| Hallucinated table/column errors | 0 of 10 SQL attempts (0.0%) |
| Grounded answers | 100.0% |
| Response time avg / p50 / p95 | 2664.1 / 1922.7 / 7504.7 ms |
| Gemini calls (total / avg) | 11 / 1.1 |
| Tokens (prompt / output) | 10,652 / 1,731 |
| Validator corpus: unsafe blocked | 25 / 25 |
| Validator corpus: safe accepted | 15 / 15 |

## Accuracy by category

| Category | Accuracy |
|---|---|
| aggregation | 100.0% |
| basic | 100.0% |
| coded values | 100.0% |
| comparison | 100.0% |
| dates | 100.0% |
| grouping | 100.0% |
| join | 100.0% |
| ranking | 100.0% |
| ratios | 0.0% |
| unsafe | 100.0% |

## Accuracy by difficulty

| Difficulty | Accuracy |
|---|---|
| easy | 100.0% |
| hard | 75.0% |
| medium | 100.0% |

## Failures (1)

- **hard-01** Which city had the highest participation rate in the 2026 exam, meaning students who registered for it divided by all students in that city? → no result rows
