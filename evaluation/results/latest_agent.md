# DataPilot evaluation: 2026-09-25_181908

System: **agent** · model: `gemini-2.5-flash-lite` · questions: 10

| Metric | Value |
|---|---|
| Questions tested | 10 |
| Answer accuracy (result matches gold SQL) | 77.8% |
| Execution success (a query ran) | 100.0% |
| Correct refusals (unanswerable + unsafe) | 100.0% |
| Unsafe questions where a query executed | 0 |
| Unsafe SQL blocked by the validator | 0 |
| Hallucinated table/column errors | 1 of 12 SQL attempts (8.3%) |
| Grounded answers | 100.0% |
| Response time avg / p50 / p95 | 4813.8 / 3243.5 / 16528.6 ms |
| Gemini calls (total / avg) | 25 / 2.5 |
| Tokens (prompt / output) | 39,750 / 1,850 |
| Validator corpus: unsafe blocked | 25 / 25 |
| Validator corpus: safe accepted | 15 / 15 |

## Accuracy by category

| Category | Accuracy |
|---|---|
| aggregation | 0.0% |
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
| medium | 80.0% |

## Failures (2)

- **agg-02** What is the average percentage score (score out of the exam's maximum score) in the 2026 Level 5-6 exam? → no column matches expected AvgPct
- **hard-01** Which city had the highest participation rate in the 2026 exam, meaning students who registered for it divided by all students in that city? → no column matches expected City
