import pytest

from datapilot import pipeline
from datapilot.database import DatabaseError, QueryResult
from datapilot.schema import ColumnInfo, DatabaseSchema, TableInfo
from datapilot.sql_generator import SqlGeneration

SCHEMA = DatabaseSchema(
    database_name="Test",
    tables=[
        TableInfo(
            schema_name="dbo",
            name="Students",
            columns=[ColumnInfo(name="StudentId", data_type="INT",
                                is_nullable=False, is_identity=True)],
        )
    ],
)


def _generation(sql: str | None, can_answer: bool = True,
                clarification: str | None = None) -> SqlGeneration:
    return SqlGeneration(can_answer=can_answer, sql=sql, tables_used=[],
                         explanation="test", clarification_needed=clarification)


@pytest.fixture
def executed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Records every SQL statement the pipeline tries to execute."""
    calls: list[str] = []

    def fake_run(sql: str, max_rows: int) -> QueryResult:
        calls.append(sql)
        return QueryResult(columns=["n"], rows=[{"n": 3000}], truncated=False)

    monkeypatch.setattr(pipeline, "run_readonly_query", fake_run)
    monkeypatch.setattr(pipeline, "generate_answer", lambda q, r: "There are 3000 students.")
    return calls


def test_unsafe_sql_is_never_executed(monkeypatch, executed) -> None:
    monkeypatch.setattr(pipeline, "generate_sql",
                        lambda q, s: _generation("DELETE FROM dbo.Students"))

    result = pipeline.answer_question("delete everything", SCHEMA)

    assert result.status == "blocked"
    assert result.validation_errors
    assert executed == []


def test_safe_sql_is_executed_and_answered(monkeypatch, executed) -> None:
    monkeypatch.setattr(pipeline, "generate_sql",
                        lambda q, s: _generation("SELECT COUNT(*) AS n FROM dbo.Students"))

    result = pipeline.answer_question("How many students?", SCHEMA)

    assert result.status == "answered"
    assert result.answer == "There are 3000 students."
    assert result.rows == [{"n": 3000}]
    assert executed == ["SELECT COUNT(*) AS n FROM dbo.Students"]


def test_cannot_answer_skips_database(monkeypatch, executed) -> None:
    monkeypatch.setattr(pipeline, "generate_sql",
                        lambda q, s: _generation(None, can_answer=False))

    result = pipeline.answer_question("What's the weather?", SCHEMA)

    assert result.status == "cannot_answer"
    assert executed == []


def test_clarification_is_returned(monkeypatch, executed) -> None:
    monkeypatch.setattr(pipeline, "generate_sql",
                        lambda q, s: _generation(None, can_answer=False,
                                                 clarification="Which data?"))

    result = pipeline.answer_question("Show me the data", SCHEMA)

    assert result.status == "needs_clarification"
    assert result.answer == "Which data?"


def test_database_error_is_reported(monkeypatch) -> None:
    def failing_run(sql: str, max_rows: int) -> QueryResult:
        raise DatabaseError("Invalid column name 'City'")

    monkeypatch.setattr(pipeline, "generate_sql",
                        lambda q, s: _generation("SELECT City FROM dbo.Students"))
    monkeypatch.setattr(pipeline, "run_readonly_query", failing_run)

    result = pipeline.answer_question("Students by city", SCHEMA)

    assert result.status == "error"
    assert "Invalid column name" in result.answer
