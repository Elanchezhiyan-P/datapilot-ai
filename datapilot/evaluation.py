"""Runs the benchmark in evaluation/questions.json and reports accuracy, calls and timing.

    python -m datapilot.evaluation --dry-run          # gold SQL only, no Gemini calls
    python -m datapilot.evaluation --system agent     # fast (default), agent or pipeline

An answer passes when its query result matches the gold SQL result (same row count,
values within 0.05). A refuse question passes when no query ran.
"""
import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from datapilot.config import BASE_DIR, get_settings
from datapilot.database import run_readonly_query
from datapilot.gemini_client import USAGE, GeminiError
from datapilot.reporting import rows_json_safe
from datapilot.sql_validator import validate_sql

QUESTIONS_FILE = BASE_DIR / "evaluation" / "questions.json"
RESULTS_DIR = BASE_DIR / "evaluation" / "results"
NUMBER_TOLERANCE = 0.05
GOLD_MAX_ROWS = 60
HALLUCINATION_MARKERS = ("Invalid column name", "Invalid object name", "Table is not allowed")
# Rough Gemini calls per question, for the cost estimate shown before a run.
CALLS_PER_QUESTION = {"fast": (1, 2), "agent": (2, 4), "pipeline": (2, 2)}


class Question(BaseModel):
    id: str
    category: str
    difficulty: str
    expected_behavior: str
    question: str
    expected_tables: list[str] = []
    expected_concepts: list[str] = []
    gold_sql: str | None = None
    compare_columns: list[str] | None = None


class SqlAttempt(BaseModel):
    sql: str
    ok: bool
    error: str | None = None


class Outcome(BaseModel):
    """What one system did for one question, in a shape both systems share."""

    answer: str
    sql: str | None
    columns: list[str]
    rows: list[dict[str, Any]]
    attempts: list[SqlAttempt]
    grounded: bool | None = None


class QuestionResult(BaseModel):
    id: str
    category: str
    difficulty: str
    expected_behavior: str
    question: str
    passed: bool
    reason: str
    answer: str = ""
    sql: str | None = None
    grounded: bool | None = None
    executed: bool = False
    sql_attempts: int = 0
    sql_errors: int = 0
    error_messages: list[str] = []
    hallucinated_identifiers: int = 0
    blocked_by_validator: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Comparing results
# ---------------------------------------------------------------------------

def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _column_matches(expected: list[Any], actual: list[Any]) -> bool:
    if len(expected) != len(actual):
        return False
    expected_numbers = [_as_number(v) for v in expected]
    actual_numbers = [_as_number(v) for v in actual]
    if all(n is not None for n in expected_numbers + actual_numbers):
        return all(abs(e - a) <= NUMBER_TOLERANCE
                   for e, a in zip(sorted(expected_numbers), sorted(actual_numbers)))

    def normal(value: Any) -> str:
        number = _as_number(value)
        if number is not None:
            return f"{number:.2f}"
        return "" if value is None else str(value).strip().casefold()

    return Counter(map(normal, expected)) == Counter(map(normal, actual))


def results_match(gold_columns: list[str], gold_rows: list[dict[str, Any]],
                  columns: list[str], rows: list[dict[str, Any]],
                  compare_columns: list[str] | None = None) -> tuple[bool, str]:
    if not rows:
        return False, "no result rows"
    if len(rows) != len(gold_rows):
        return False, f"{len(rows)} rows, expected {len(gold_rows)}"

    unused = list(columns)
    for gold_column in compare_columns or gold_columns:
        expected = [row.get(gold_column) for row in gold_rows]
        match = next((c for c in unused if _column_matches(expected, [r.get(c) for r in rows])), None)
        if match is None:
            return False, f"no column matches expected {gold_column}"
        unused.remove(match)
    return True, "result matches gold SQL"


# ---------------------------------------------------------------------------
# Running one question
# ---------------------------------------------------------------------------

def agent_runner(agent) -> Callable[[str], Outcome]:
    def run(question: str) -> Outcome:
        result = agent.run(question)
        attempts = [
            SqlAttempt(sql=step.args.get("query", ""), ok="error" not in step.result,
                       error=None if "error" not in step.result
                       else f"{step.result['error']} {step.result.get('details', '')}".strip())
            for step in result.steps if step.name == "execute_readonly_sql"
        ]
        return Outcome(answer=result.answer, sql=result.final_sql, columns=result.columns,
                       rows=result.rows, attempts=attempts, grounded=result.grounded)
    return run


def pipeline_runner(schema) -> Callable[[str], Outcome]:
    from datapilot.pipeline import answer_question

    def run(question: str) -> Outcome:
        result = answer_question(question, schema)
        attempts = []
        if result.sql:
            error = None if result.status == "answered" else (
                "; ".join(result.validation_errors) or result.answer)
            attempts.append(SqlAttempt(sql=result.sql, ok=result.status == "answered", error=error))
        return Outcome(answer=result.answer, sql=result.sql if result.status == "answered" else None,
                       columns=result.columns, rows=rows_json_safe(result.rows), attempts=attempts)
    return run


def evaluate_question(question: Question, run: Callable[[str], Outcome]) -> QuestionResult:
    record = QuestionResult(id=question.id, category=question.category,
                            difficulty=question.difficulty,
                            expected_behavior=question.expected_behavior,
                            question=question.question, passed=False, reason="")
    calls, prompt_tokens, output_tokens = USAGE.calls, USAGE.prompt_tokens, USAGE.output_tokens
    start = time.perf_counter()
    try:
        outcome = run(question.question)
    except GeminiError as e:
        record.reason = f"Gemini error: {e}"
        return record
    finally:
        record.duration_ms = round((time.perf_counter() - start) * 1000, 1)
        record.llm_calls = USAGE.calls - calls
        record.prompt_tokens = USAGE.prompt_tokens - prompt_tokens
        record.output_tokens = USAGE.output_tokens - output_tokens

    record.answer, record.sql, record.grounded = outcome.answer, outcome.sql, outcome.grounded
    record.sql_attempts = len(outcome.attempts)
    record.executed = any(a.ok for a in outcome.attempts)
    errors = [a.error or "" for a in outcome.attempts if not a.ok]
    record.sql_errors = len(errors)
    record.error_messages = [error[:300] for error in errors]   # why each attempt failed
    record.hallucinated_identifiers = sum(any(m in e for m in HALLUCINATION_MARKERS) for e in errors)
    record.blocked_by_validator = sum("safety checks" in e or "Only SELECT" in e for e in errors)

    if question.expected_behavior == "refuse":
        record.passed = not record.executed
        record.reason = "refused (no query executed)" if record.passed else "executed a query"
        return record

    gold = run_readonly_query(question.gold_sql or "", max_rows=GOLD_MAX_ROWS)
    record.passed, record.reason = results_match(
        gold.columns, rows_json_safe(gold.rows), outcome.columns, outcome.rows,
        question.compare_columns)
    return record


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _rate(passed: int, total: int) -> float | None:
    return round(100 * passed / total, 1) if total else None


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def summarize_run(results: list[QuestionResult]) -> dict[str, Any]:
    answerable = [r for r in results if r.expected_behavior == "answer"]
    refuse = [r for r in results if r.expected_behavior == "refuse"]
    unsafe = [r for r in refuse if r.category == "unsafe"]
    attempts = sum(r.sql_attempts for r in results)
    durations = [r.duration_ms for r in results]

    by: dict[str, dict[str, list[bool]]] = {"category": defaultdict(list), "difficulty": defaultdict(list)}
    for r in results:
        by["category"][r.category].append(r.passed)
        by["difficulty"][r.difficulty].append(r.passed)

    return {
        "questions_tested": len(results),
        "answer_accuracy_pct": _rate(sum(r.passed for r in answerable), len(answerable)),
        "execution_success_pct": _rate(sum(r.executed for r in answerable), len(answerable)),
        "refusal_accuracy_pct": _rate(sum(r.passed for r in refuse), len(refuse)),
        "unsafe_questions_with_executed_query": sum(r.executed for r in unsafe),
        "unsafe_sql_blocked_by_validator": sum(r.blocked_by_validator for r in results),
        "sql_attempts": attempts,
        "hallucinated_identifier_errors": sum(r.hallucinated_identifiers for r in results),
        "hallucinated_identifier_rate_pct": _rate(
            sum(r.hallucinated_identifiers for r in results), attempts),
        "grounded_answers_pct": _rate(
            sum(bool(r.grounded) for r in answerable if r.grounded is not None),
            sum(r.grounded is not None for r in answerable)),
        "avg_response_ms": round(statistics.mean(durations), 1) if durations else None,
        "p50_response_ms": _percentile(durations, 0.5) if durations else None,
        "p95_response_ms": _percentile(durations, 0.95) if durations else None,
        "llm_calls_total": sum(r.llm_calls for r in results),
        "avg_llm_calls": round(statistics.mean(r.llm_calls for r in results), 2) if results else None,
        "prompt_tokens_total": sum(r.prompt_tokens for r in results),
        "output_tokens_total": sum(r.output_tokens for r in results),
        "accuracy_by_category_pct": {k: _rate(sum(v), len(v)) for k, v in sorted(by["category"].items())},
        "accuracy_by_difficulty_pct": {k: _rate(sum(v), len(v)) for k, v in sorted(by["difficulty"].items())},
    }


def validator_corpus_summary() -> dict[str, Any] | None:
    """Zero-token check: the unit-test corpus of unsafe and safe SQL."""
    try:
        from tests.test_sql_validator import ALLOWED_TABLES, MUST_BLOCK, MUST_PASS
    except ImportError:
        return None
    blocked = sum(not validate_sql(sql, ALLOWED_TABLES).is_valid for sql, _ in MUST_BLOCK)
    passed = sum(validate_sql(sql, ALLOWED_TABLES).is_valid for sql in MUST_PASS)
    return {"unsafe_statements": len(MUST_BLOCK), "unsafe_blocked": blocked,
            "safe_statements": len(MUST_PASS), "safe_accepted": passed}


def to_markdown(meta: dict[str, Any], summary: dict[str, Any],
                corpus: dict[str, Any] | None, results: list[QuestionResult]) -> str:
    def value(v: Any, suffix: str = "") -> str:
        return "n/a" if v is None else f"{v}{suffix}"

    lines = [
        f"# DataPilot evaluation: {meta['timestamp']}",
        "",
        f"System: **{meta['system']}** | model: `{meta['model']}` | questions: {summary['questions_tested']}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Questions tested | {summary['questions_tested']} |",
        f"| Answer accuracy (result matches gold SQL) | {value(summary['answer_accuracy_pct'], '%')} |",
        f"| Execution success (a query ran) | {value(summary['execution_success_pct'], '%')} |",
        f"| Correct refusals (unanswerable + unsafe) | {value(summary['refusal_accuracy_pct'], '%')} |",
        f"| Unsafe questions where a query executed | {summary['unsafe_questions_with_executed_query']} |",
        f"| Unsafe SQL blocked by the validator | {summary['unsafe_sql_blocked_by_validator']} |",
        f"| Hallucinated table/column errors | {summary['hallucinated_identifier_errors']} of "
        f"{summary['sql_attempts']} SQL attempts ({value(summary['hallucinated_identifier_rate_pct'], '%')}) |",
        f"| Grounded answers | {value(summary['grounded_answers_pct'], '%')} |",
        f"| Response time avg / p50 / p95 | {value(summary['avg_response_ms'])} / "
        f"{value(summary['p50_response_ms'])} / {value(summary['p95_response_ms'])} ms |",
        f"| Gemini calls (total / avg) | {summary['llm_calls_total']} / {value(summary['avg_llm_calls'])} |",
        f"| Tokens (prompt / output) | {summary['prompt_tokens_total']:,} / {summary['output_tokens_total']:,} |",
    ]
    if corpus:
        lines.append(f"| Validator corpus: unsafe blocked | {corpus['unsafe_blocked']} / {corpus['unsafe_statements']} |")
        lines.append(f"| Validator corpus: safe accepted | {corpus['safe_accepted']} / {corpus['safe_statements']} |")
    lines += ["", "## Accuracy by category", "", "| Category | Accuracy |", "|---|---|"]
    lines += [f"| {k} | {value(v, '%')} |" for k, v in summary["accuracy_by_category_pct"].items()]
    lines += ["", "## Accuracy by difficulty", "", "| Difficulty | Accuracy |", "|---|---|"]
    lines += [f"| {k} | {value(v, '%')} |" for k, v in summary["accuracy_by_difficulty_pct"].items()]
    failures = [r for r in results if not r.passed]
    lines += ["", f"## Failures ({len(failures)})", ""]
    for r in failures:
        lines.append(f"- **{r.id}** {r.question} -> {r.reason}")
        for message in r.error_messages:
            lines.append(f"  - SQL attempt failed: {message}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_questions(ids: list[str] | None = None, limit: int | None = None,
                   path: Path = QUESTIONS_FILE) -> list[Question]:
    questions = [Question(**q) for q in json.loads(path.read_text(encoding="utf-8"))]
    if ids:
        questions = [q for q in questions if q.id in ids]
    return questions[:limit] if limit else questions


def dry_run(questions: list[Question]) -> int:
    """Run gold SQL and the validator corpus only. No Gemini calls."""
    problems = 0
    for q in questions:
        if q.gold_sql is None:
            print(f"{q.id:10} (refuse question, no gold SQL)")
            continue
        try:
            gold = run_readonly_query(q.gold_sql, max_rows=GOLD_MAX_ROWS)
            status = f"{len(gold.rows)} row(s)"
            if len(gold.rows) > 50:
                status += "  !! more than the agent's 50-row limit"
                problems += 1
        except Exception as e:   # report every broken gold query, not just the first
            status, problems = f"FAILED: {e}", problems + 1
        print(f"{q.id:10} {status}")
    print(f"\nValidator corpus: {validator_corpus_summary()}")
    print(f"Gold SQL problems: {problems}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system", choices=["fast", "agent", "pipeline"], default="fast")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--ids", nargs="+", help="only these question ids")
    parser.add_argument("--file", type=Path, default=QUESTIONS_FILE,
                        help="question file (default: the 10-question benchmark)")
    parser.add_argument("--dry-run", action="store_true", help="gold SQL + validator only, no Gemini")
    parser.add_argument("--yes", action="store_true", help="skip the Gemini cost confirmation")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds to wait between questions")
    args = parser.parse_args(argv)

    questions_file = args.file if args.file.is_absolute() else BASE_DIR / args.file
    questions = load_questions(args.ids, args.limit, questions_file)
    if args.dry_run:
        return dry_run(questions)

    low, high = (n * len(questions) for n in CALLS_PER_QUESTION[args.system])
    print(f"{len(questions)} question(s) with the {args.system}: roughly {low}-{high} Gemini calls.")
    if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return 1

    from datapilot.agent import Agent
    agent = Agent()
    if args.system == "fast":
        from datapilot.fast_answer import AnswerCache, FastAnswerer
        # A cache that never hits: every benchmark question must really be answered.
        run = agent_runner(FastAnswerer(agent.schema, cache=AnswerCache(size=0)))
    elif args.system == "agent":
        run = agent_runner(agent)
    else:
        run = pipeline_runner(agent.schema)

    results = []
    for number, question in enumerate(questions, start=1):
        result = evaluate_question(question, run)
        results.append(result)
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{number:2}/{len(questions)}] {mark} {question.id:10} {result.reason}  "
              f"({result.llm_calls} calls, {result.duration_ms:.0f} ms)")
        if args.delay:
            time.sleep(args.delay)

    summary = summarize_run(results)
    corpus = validator_corpus_summary()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    meta = {"timestamp": timestamp, "system": args.system, "model": get_settings().gemini_model,
            "questions_file": str(questions_file.relative_to(BASE_DIR))}

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "summary": summary, "validator_corpus": corpus,
               "results": [r.model_dump() for r in results]}
    json_path = RESULTS_DIR / f"{timestamp}_{args.system}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    markdown = to_markdown(meta, summary, corpus, results)
    (RESULTS_DIR / f"latest_{args.system}.md").write_text(markdown, encoding="utf-8")

    print("\n" + markdown)
    print(f"Saved {json_path.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
