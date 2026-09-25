# DataPilot evaluation: 2026-09-25_181950

System: **pipeline** · model: `gemini-2.5-flash-lite` · questions: 10

| Metric | Value |
|---|---|
| Questions tested | 10 |
| Answer accuracy (result matches gold SQL) | 100.0% |
| Execution success (a query ran) | 100.0% |
| Correct refusals (unanswerable + unsafe) | 100.0% |
| Unsafe questions where a query executed | 0 |
| Unsafe SQL blocked by the validator | 0 |
| Hallucinated table/column errors | 0 of 9 SQL attempts (0.0%) |
| Grounded answers | n/a |
| Response time avg / p50 / p95 | 3192.4 / 2767.4 / 4767.8 ms |
| Gemini calls (total / avg) | 19 / 1.9 |
| Tokens (prompt / output) | 10,097 / 1,980 |
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
| ratios | 100.0% |
| unsafe | 100.0% |

## Accuracy by difficulty

| Difficulty | Accuracy |
|---|---|
| easy | 100.0% |
| hard | 100.0% |
| medium | 100.0% |

## Failures (0)

