from typing import Any

import pytest
from google.genai import types

from datapilot import agent as agent_module
from datapilot import tool_calling, tools
from datapilot.agent import Agent, HistoryTurn, build_question_message
from datapilot.database import DatabaseError, QueryResult
from datapilot.schema import ColumnInfo, DatabaseSchema, TableInfo

SCHEMA = DatabaseSchema(
    database_name="Test",
    tables=[
        TableInfo(
            schema_name="dbo",
            name="Schools",
            columns=[
                ColumnInfo(name="SchoolId", data_type="INT", is_nullable=False, is_identity=True),
                ColumnInfo(name="City", data_type="NVARCHAR(50)", is_nullable=False, is_identity=False),
            ],
        )
    ],
)


def _call(name: str, **args: Any) -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(name=name, args=args))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


def _text(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(
            role="model", parts=[types.Part.from_text(text=text)]))]
    )


@pytest.fixture
def executed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_run(sql: str, max_rows: int) -> QueryResult:
        calls.append(sql)
        if "BadColumn" in sql:
            raise DatabaseError("Invalid column name 'BadColumn'.")
        if "GROUP BY [City]" in sql:
            return QueryResult(columns=["value", "row_count"],
                               rows=[{"value": "Coimbatore", "row_count": 5}], truncated=False)
        return QueryResult(columns=["StudentCount"], rows=[{"StudentCount": 409}], truncated=False)

    monkeypatch.setattr(tools, "run_readonly_query", fake_run)
    return calls


def _script(monkeypatch: pytest.MonkeyPatch, responses: list[types.GenerateContentResponse]):
    sent: list[list[types.Content]] = []

    def fake_generate(contents, declarations, system_instruction):
        sent.append(list(contents))
        return responses[len(sent) - 1]

    monkeypatch.setattr(tool_calling, "generate_with_tools", fake_generate)
    return sent


QUERY = "SELECT COUNT(*) AS StudentCount FROM dbo.Schools"


def test_grounded_answer_is_accepted(monkeypatch, executed) -> None:
    _script(monkeypatch, [
        _call("get_database_schema"),
        _call("execute_readonly_sql", query=QUERY),
        _text("There are 409 students."),
    ])

    result = Agent(SCHEMA).run("How many students?")

    assert result.grounded
    assert result.final_sql == QUERY
    assert result.rows == [{"StudentCount": 409}]
    assert result.llm_calls == 3


def test_ungrounded_answer_is_sent_back_and_fixed(monkeypatch, executed) -> None:
    sent = _script(monkeypatch, [
        _call("get_database_schema"),
        _call("execute_readonly_sql", query=QUERY),
        _text("There are 512 students."),          # invented number
        _text("There are 409 students."),          # corrected after verification
    ])

    result = Agent(SCHEMA).run("How many students?")

    assert result.grounded
    assert result.answer == "There are 409 students."
    verification = sent[3][-1].parts[0].text
    assert "512" in verification


def test_still_ungrounded_answer_is_flagged(monkeypatch, executed) -> None:
    _script(monkeypatch, [
        _call("get_database_schema"),
        _call("execute_readonly_sql", query=QUERY),
        _text("There are 512 students."),
        _text("There are 512 students."),
    ])

    result = Agent(SCHEMA).run("How many students?")

    assert not result.grounded
    assert result.ungrounded_numbers == ["512"]


def test_giving_up_after_an_error_triggers_recovery(monkeypatch, executed) -> None:
    bad_query = "SELECT BadColumn FROM dbo.Schools"
    sent = _script(monkeypatch, [
        _call("execute_readonly_sql", query=bad_query),
        _text("The query failed, please check the schema."),
        _call("execute_readonly_sql", query=QUERY),
        _text("There are 409 students."),
    ])

    result = Agent(SCHEMA).run("How many students?")

    assert result.answer == "There are 409 students."
    assert "Do not give up" in sent[2][-1].parts[0].text
    assert executed == [bad_query, QUERY]


def test_schema_is_in_the_agent_instructions() -> None:
    assert "dbo.Schools" in Agent(SCHEMA).system_instruction


def test_distinct_values_tool_uses_schema_identifiers(executed) -> None:
    result = tools.ToolBox(SCHEMA).get_distinct_values("schools", "city")

    assert result["values"] == [{"value": "Coimbatore", "row_count": 5}]
    assert executed == [
        "SELECT TOP (50) [City] AS value, COUNT(*) AS row_count "
        "FROM [dbo].[Schools] GROUP BY [City] ORDER BY COUNT(*) DESC"
    ]


def test_distinct_values_rejects_unknown_column(executed) -> None:
    result = tools.ToolBox(SCHEMA).get_distinct_values("dbo.Schools", "Name]; DROP TABLE x--")

    assert "no column" in result["error"]
    assert executed == []


def test_history_goes_into_the_user_message_not_model_turns() -> None:
    message = build_question_message(
        "What about Coimbatore?",
        [HistoryTurn(question="Participation in 2026?", answer="2243.", sql="SELECT 1")],
    )

    assert message.role == "user"
    text = message.parts[0].text
    assert "Participation in 2026?" in text and "SQL: SELECT 1" in text
    assert text.endswith("Current question: What about Coimbatore?")


def test_empty_answer_falls_back_to_answer_generator(monkeypatch, executed) -> None:
    _script(monkeypatch, [
        _call("execute_readonly_sql", query=QUERY),
        _text(""),
        _text(""),   # still empty after the loop's nudge
    ])
    monkeypatch.setattr(agent_module, "generate_answer", lambda q, r: "There are 409 students.")

    result = Agent(SCHEMA).run("How many students?")

    assert result.answer == "There are 409 students."
    assert result.grounded
