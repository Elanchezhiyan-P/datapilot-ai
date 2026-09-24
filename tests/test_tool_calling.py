from typing import Any

import pytest
from google.genai import types

from datapilot import tool_calling, tools
from datapilot.database import QueryResult
from datapilot.schema import ColumnInfo, DatabaseSchema, TableInfo

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


def _call(name: str, **args: Any) -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(name=name, args=args))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


def _text(text: str) -> types.GenerateContentResponse:
    part = types.Part.from_text(text=text)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


@pytest.fixture
def executed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_run(sql: str, max_rows: int) -> QueryResult:
        calls.append(sql)
        return QueryResult(columns=["n"], rows=[{"n": 3000}], truncated=False)

    monkeypatch.setattr(tools, "run_readonly_query", fake_run)
    return calls


def _script(monkeypatch: pytest.MonkeyPatch, responses: list[types.GenerateContentResponse]):
    """Make the fake Gemini return these responses in order, and record what it was sent."""
    sent: list[list[types.Content]] = []

    def fake_generate(contents, declarations, system_instruction):
        sent.append(list(contents))
        return responses[len(sent) - 1]

    monkeypatch.setattr(tool_calling, "generate_with_tools", fake_generate)
    return sent


def test_runs_requested_tools_and_returns_answer(monkeypatch, executed) -> None:
    sent = _script(monkeypatch, [
        _call("get_database_schema"),
        _call("execute_readonly_sql", query="SELECT COUNT(*) AS n FROM dbo.Students"),
        _text("There are 3000 students."),
    ])

    result = tool_calling.run_with_tools("How many students?", SCHEMA)

    assert result.answer == "There are 3000 students."
    assert result.turns == 3
    assert executed == ["SELECT COUNT(*) AS n FROM dbo.Students"]
    # The third request must carry the SQL result back to the model.
    last_turn = sent[2][-1]
    assert last_turn.parts[0].function_response.response["rows"] == [{"n": 3000}]


def test_sql_before_schema_lookup_is_refused(monkeypatch, executed) -> None:
    _script(monkeypatch, [
        _call("execute_readonly_sql", query="SELECT COUNT(*) AS n FROM dbo.Students"),
        _text("Let me check."),
    ])

    result = tool_calling.run_with_tools("How many students?", SCHEMA)

    assert executed == []
    assert "schema first" in result.tool_calls[0].result["error"]


def test_empty_answer_gets_one_nudge(monkeypatch, executed) -> None:
    sent = _script(monkeypatch, [_text(""), _text("There are 3000 students.")])

    result = tool_calling.run_with_tools("How many students?", SCHEMA)

    assert result.answer == "There are 3000 students."
    assert sent[1][-1].parts[0].text == tool_calling.EMPTY_ANSWER_NUDGE


def test_unsafe_sql_from_model_is_rejected_not_executed(monkeypatch, executed) -> None:
    _script(monkeypatch, [
        _call("execute_readonly_sql", query="DELETE FROM dbo.Students"),
        _text("I cannot do that."),
    ])

    result = tool_calling.run_with_tools("delete everything", SCHEMA)

    assert executed == []
    assert "rejected" in result.tool_calls[0].result["error"]


def test_unknown_tool_returns_error_to_model(monkeypatch, executed) -> None:
    _script(monkeypatch, [_call("drop_database"), _text("Sorry.")])

    result = tool_calling.run_with_tools("anything", SCHEMA)

    assert "Unknown tool" in result.tool_calls[0].result["error"]


def test_stops_at_turn_limit(monkeypatch, executed) -> None:
    _script(monkeypatch, [_call("get_relationships")] * tool_calling.MAX_TURNS)

    result = tool_calling.run_with_tools("loop forever", SCHEMA)

    assert result.stopped_early
    assert len(result.tool_calls) == tool_calling.MAX_TURNS


def test_get_table_schema_accepts_unqualified_name() -> None:
    result = tools.ToolBox(SCHEMA).get_table_schema("students")
    assert result["table"] == "dbo.Students"
