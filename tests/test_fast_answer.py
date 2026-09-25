"""Fast mode: one Gemini call per question. Gemini and the database are faked."""
import pytest

from datapilot import fast_answer
from datapilot.agent import HistoryTurn
from datapilot.database import DatabaseError, QueryResult
from datapilot.fast_answer import (FastAnswerer, FastPlan, fallback_answer, fill_template,
                                   format_value)
from datapilot.schema import ColumnInfo, DatabaseSchema, ForeignKeyInfo, TableInfo


def _column(name: str) -> ColumnInfo:
    return ColumnInfo(name=name, data_type="INT", is_nullable=False, is_identity=False)


SCHEMA = DatabaseSchema(database_name="Test", tables=[
    TableInfo(schema_name="dbo", name="Schools", columns=[_column("SchoolId"), _column("City")]),
    TableInfo(schema_name="dbo", name="Students", columns=[_column("StudentId"), _column("SchoolId")],
              foreign_keys=[ForeignKeyInfo(column="SchoolId", references_table="dbo.Schools",
                                           references_column="SchoolId")]),
])
GOOD_SQL = ("SELECT COUNT(*) AS Students FROM dbo.Students s "
            "JOIN dbo.Schools sc ON sc.SchoolId = s.SchoolId WHERE sc.City = 'Coimbatore'")


def _plan(sql=GOOD_SQL, template="{Students} students attend schools in Coimbatore.", **kw) -> FastPlan:
    return FastPlan(can_answer=kw.get("can_answer", True), sql=sql, answer_template=template,
                    clarification_needed=kw.get("clarification"))


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch):
    """Scripted Gemini: returns the queued plans in order and records every prompt."""
    calls: list[str] = []
    queue: list[FastPlan] = []

    def fake_ask_structured(prompt, schema, system_instruction=None):
        calls.append(prompt)
        return queue.pop(0)

    monkeypatch.setattr(fast_answer, "ask_structured", fake_ask_structured)
    return calls, queue


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch):
    executed: list[str] = []

    def fake_run(sql: str, max_rows: int) -> QueryResult:
        executed.append(sql)
        if "BadColumn" in sql:
            raise DatabaseError("Invalid column name 'BadColumn'.")
        return QueryResult(columns=["Students"], rows=[{"Students": 409}], truncated=False)

    monkeypatch.setattr(fast_answer, "run_readonly_query", fake_run)
    return executed


# --- template filling ---------------------------------------------------------

def test_placeholders_are_filled_from_the_first_row() -> None:
    rows = [{"City": "Coimbatore", "Students": 409}, {"City": "Madurai", "Students": 408}]
    filled = fill_template("{City} leads with {Students} students across {row_count} cities.",
                           ["City", "Students"], rows)
    assert filled == "Coimbatore leads with 409 students across 2 cities."


def test_numbers_are_formatted_but_years_are_not() -> None:
    assert format_value("TotalPaid", "1088500.00") == "1,088,500"
    assert format_value("AvgPct", 65.1283) == "65.13"
    assert format_value("ExamYear", 2026) == "2026"
    assert format_value("StudentId", 1234) == "1234"
    assert format_value("student_id", 1234) == "1234"


def test_unknown_placeholder_means_the_template_is_not_used() -> None:
    assert fill_template("{Missing} students", ["Students"], [{"Students": 1}]) is None


def test_fallback_answers_from_data_alone() -> None:
    assert fallback_answer(["Students"], [{"Students": 409}]) == "The result is 409."
    assert fallback_answer(["City"], []) == "No matching data was found for that question."


# --- answering ------------------------------------------------------------------

def test_a_normal_question_takes_one_gemini_call(gemini, database) -> None:
    calls, queue = gemini
    queue.append(_plan())

    result = FastAnswerer(SCHEMA).run("How many students attend schools in Coimbatore?")

    assert result.answer == "409 students attend schools in Coimbatore."
    assert result.llm_calls == 1 and len(calls) == 1
    assert result.final_sql == GOOD_SQL and result.rows == [{"Students": 409}]
    assert result.grounded and result.mode == "fast"


def test_a_repeated_question_is_answered_from_the_cache(gemini, database) -> None:
    calls, queue = gemini
    queue.append(_plan())
    answerer = FastAnswerer(SCHEMA)

    answerer.run("How many students attend schools in Coimbatore?")
    again = answerer.run("  how many students attend schools in coimbatore  ")

    assert again.cached and again.llm_calls == 0
    assert len(calls) == 1 and len(database) == 1   # no second Gemini call, no second query
    assert again.answer == "409 students attend schools in Coimbatore."


def test_same_words_in_a_different_conversation_context_are_not_cached(gemini, database) -> None:
    calls, queue = gemini
    queue.extend([_plan(), _plan()])
    answerer = FastAnswerer(SCHEMA)

    answerer.run("What about 2025?", [HistoryTurn(question="a", answer="b", sql="SELECT 1")])
    answerer.run("What about 2025?", [HistoryTurn(question="a", answer="b", sql="SELECT 2")])

    assert len(calls) == 2


def test_standalone_question_is_cached_even_after_the_conversation_moves_on(gemini, database) -> None:
    # Seen live: the repeat missed the cache because three new turns changed the context.
    calls, queue = gemini
    queue.append(_plan())
    answerer = FastAnswerer(SCHEMA)
    question = "How many students attend schools in Coimbatore?"

    answerer.run(question)
    later = [HistoryTurn(question="Monthly registrations", answer="…", sql="SELECT 2")]
    again = answerer.run(question, later)

    assert again.cached and len(calls) == 1


def test_follow_up_detection() -> None:
    assert fast_answer.looks_like_follow_up("what about coimbatore")
    assert fast_answer.looks_like_follow_up("compare it with 2025")
    assert not fast_answer.looks_like_follow_up("how many students attend schools in coimbatore")


def test_months_read_as_names_in_sentences() -> None:
    # Seen live: "There were 301 registrations in 12 of 2025."
    rows = [{"RegistrationYear": 2025, "RegistrationMonth": 12, "RegistrationCount": 301}]
    filled = fill_template("There were {RegistrationCount} registrations in {RegistrationMonth} {RegistrationYear}.",
                           ["RegistrationYear", "RegistrationMonth", "RegistrationCount"], rows)
    assert filled == "There were 301 registrations in December 2025."


def test_unsafe_sql_is_never_run_and_is_repaired_once(gemini, database) -> None:
    calls, queue = gemini
    queue.extend([_plan(sql="DELETE FROM dbo.Students"), _plan()])

    result = FastAnswerer(SCHEMA).run("How many students attend schools in Coimbatore?")

    assert database == [GOOD_SQL]            # the DELETE never reached the database
    assert result.llm_calls == 2
    assert "Only SELECT" in calls[1]          # the repair prompt explains the problem
    assert result.steps[0].result["error"] == "Query rejected by safety checks."


def test_a_wrong_join_is_repaired(gemini, database) -> None:
    calls, queue = gemini
    bad_join = ("SELECT COUNT(*) AS Students FROM dbo.Students s "
                "JOIN dbo.Schools sc ON sc.SchoolId = s.StudentId")
    queue.extend([_plan(sql=bad_join), _plan()])

    result = FastAnswerer(SCHEMA).run("How many students attend schools in Coimbatore?")

    assert database == [GOOD_SQL] and result.llm_calls == 2


def test_database_error_gets_one_repair_then_gives_up(gemini, database) -> None:
    calls, queue = gemini
    bad = "SELECT BadColumn FROM dbo.Students"
    queue.extend([_plan(sql=bad), _plan(sql=bad)])

    result = FastAnswerer(SCHEMA).run("How many?")

    assert result.llm_calls == 2              # never more than one repair
    assert result.final_sql is None and "couldn't write a working query" in result.answer


def test_invented_number_in_the_template_is_replaced(gemini, database) -> None:
    calls, queue = gemini
    queue.append(_plan(template="{Students} students, up 12 from last year."))   # 12 is made up

    result = FastAnswerer(SCHEMA).run("How many students attend schools in Coimbatore?")

    assert result.answer == "The result is 409."
    assert result.grounded


def test_refusal_makes_no_query(gemini, database) -> None:
    calls, queue = gemini
    queue.append(_plan(sql=None, template="I can't change data.", can_answer=False))

    result = FastAnswerer(SCHEMA).run("Delete all students")

    assert result.answer == "I can't change data." and database == [] and result.llm_calls == 1


def test_schema_is_in_the_instructions() -> None:
    assert "dbo.Students" in FastAnswerer(SCHEMA).system_instruction
