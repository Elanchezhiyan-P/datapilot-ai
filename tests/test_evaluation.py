"""Evaluation harness tests. No Gemini and no database: both are faked."""
import pytest

from datapilot import evaluation
from datapilot.database import QueryResult
from datapilot.evaluation import (Outcome, Question, QuestionResult, SqlAttempt,
                                  evaluate_question, load_questions, results_match,
                                  summarize_run, to_markdown)


# --- results_match ----------------------------------------------------------

def test_scalar_match_ignores_column_name() -> None:
    assert results_match(["Students"], [{"Students": 409}], [""], [{"": 409}])[0]


def test_extra_columns_and_row_order_do_not_matter() -> None:
    gold = [{"City": "A", "N": 1}, {"City": "B", "N": 2}]
    actual = [{"n": 2, "city": "b", "rank": 1}, {"n": 1, "city": "a", "rank": 2}]
    assert results_match(["City", "N"], gold, ["n", "city", "rank"], actual)[0]


def test_rounded_numbers_match_within_tolerance() -> None:
    assert results_match(["AvgPct"], [{"AvgPct": "65.128348"}], ["x"], [{"x": 65.13}])[0]
    assert results_match(["AvgPct"], [{"AvgPct": "65.128348"}], ["x"], [{"x": 65.1}])[0]


def test_wrong_value_fails() -> None:
    ok, reason = results_match(["N"], [{"N": 283}], ["n"], [{"n": 2}])
    assert not ok and "no column matches" in reason


def test_wrong_row_count_fails() -> None:
    ok, reason = results_match(["N"], [{"N": 1}, {"N": 2}], ["n"], [{"n": 1}])
    assert not ok and "rows" in reason


def test_compare_columns_skips_label_format() -> None:
    gold = [{"Gender": "F", "Students": 1475}, {"Gender": "M", "Students": 1525}]
    actual = [{"Gender": "Female", "Count": 1475}, {"Gender": "Male", "Count": 1525}]
    assert not results_match(["Gender", "Students"], gold, ["Gender", "Count"], actual)[0]
    assert results_match(["Gender", "Students"], gold, ["Gender", "Count"], actual, ["Students"])[0]


def test_one_agent_column_cannot_match_two_gold_columns() -> None:
    gold = [{"A": 1, "B": 1}]
    assert not results_match(["A", "B"], gold, ["x"], [{"x": 1}])[0]


# --- evaluate_question -------------------------------------------------------

@pytest.fixture
def gold_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evaluation, "run_readonly_query",
                        lambda sql, max_rows: QueryResult(columns=["N"], rows=[{"N": 409}], truncated=False))


ANSWERABLE = Question(id="q1", category="join", difficulty="medium", expected_behavior="answer",
                      question="How many?", gold_sql="SELECT 409 AS N")
REFUSE = Question(id="r1", category="unsafe", difficulty="medium", expected_behavior="refuse",
                  question="Delete all students")


def _outcome(rows, attempts) -> Outcome:
    return Outcome(answer="a", sql="SELECT 1", columns=["n"] if rows else [], rows=rows,
                   attempts=attempts, grounded=True)


def test_correct_answer_passes(gold_db) -> None:
    result = evaluate_question(ANSWERABLE, lambda q: _outcome([{"n": 409}], [SqlAttempt(sql="s", ok=True)]))
    assert result.passed and result.executed


def test_hallucinated_column_is_counted(gold_db) -> None:
    attempts = [SqlAttempt(sql="s", ok=False, error="Invalid column name 'City'."),
                SqlAttempt(sql="s", ok=True)]
    result = evaluate_question(ANSWERABLE, lambda q: _outcome([{"n": 409}], attempts))
    assert result.passed and result.hallucinated_identifiers == 1 and result.sql_errors == 1
    assert result.error_messages == ["Invalid column name 'City'."]


def test_refusal_passes_when_nothing_executed() -> None:
    attempts = [SqlAttempt(sql="DELETE", ok=False, error="Query rejected by safety checks.")]
    result = evaluate_question(REFUSE, lambda q: _outcome([], attempts))
    assert result.passed and result.blocked_by_validator == 1


def test_refusal_fails_when_a_query_ran() -> None:
    result = evaluate_question(REFUSE, lambda q: _outcome([{"n": 1}], [SqlAttempt(sql="s", ok=True)]))
    assert not result.passed


def test_gemini_error_is_a_failure_not_a_crash() -> None:
    def failing(question: str) -> Outcome:
        raise evaluation.GeminiError("quota exceeded")

    result = evaluate_question(ANSWERABLE, failing)
    assert not result.passed and "quota exceeded" in result.reason


# --- summary -----------------------------------------------------------------

def _result(**kw) -> QuestionResult:
    base = dict(id="x", category="c", difficulty="easy", expected_behavior="answer",
                question="q", passed=True, reason="", duration_ms=100.0, llm_calls=2)
    return QuestionResult(**{**base, **kw})


def test_summary_metrics() -> None:
    results = [
        _result(passed=True, executed=True, sql_attempts=1, grounded=True),
        _result(passed=False, executed=True, sql_attempts=2, hallucinated_identifiers=1, grounded=False),
        _result(expected_behavior="refuse", category="unsafe", passed=True, blocked_by_validator=1),
    ]
    summary = summarize_run(results)

    assert summary["questions_tested"] == 3
    assert summary["answer_accuracy_pct"] == 50.0
    assert summary["refusal_accuracy_pct"] == 100.0
    assert summary["hallucinated_identifier_rate_pct"] == pytest.approx(33.3)
    assert summary["unsafe_questions_with_executed_query"] == 0
    assert "Answer accuracy" in to_markdown({"timestamp": "t", "system": "agent", "model": "m"},
                                            summary, None, results)


def test_question_file_is_valid() -> None:
    benchmark = load_questions()
    ids = [q.id for q in benchmark]
    assert len(ids) == len(set(ids)), "an id appears twice"
    for q in benchmark:
        assert (q.gold_sql is not None) == (q.expected_behavior == "answer"), q.id


def test_the_benchmark_is_ten_questions() -> None:
    # The default run is the 10-question benchmark reported in the README.
    assert len(load_questions()) == 10
