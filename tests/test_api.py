import pytest
from fastapi.testclient import TestClient

from datapilot import api
from datapilot.agent import AgentResult, HistoryTurn
from datapilot.schema import ColumnInfo, DatabaseSchema, TableInfo
from datapilot.tool_calling import ToolCallRecord

SCHEMA = DatabaseSchema(
    database_name="Test",
    tables=[TableInfo(schema_name="dbo", name="Students",
                      columns=[ColumnInfo(name="StudentId", data_type="INT",
                                          is_nullable=False, is_identity=True)])],
)
SQL = "SELECT COUNT(*) AS n FROM dbo.Students"


class FakeAgent:
    schema = SCHEMA

    def __init__(self) -> None:
        self.histories: list[list[HistoryTurn]] = []

    def run(self, question: str, history: list[HistoryTurn] | None = None) -> AgentResult:
        self.histories.append(list(history or []))
        step = ToolCallRecord(name="execute_readonly_sql", args={"query": SQL},
                              result={"columns": ["n"], "rows": [{"n": 3000}], "row_count": 1},
                              duration_ms=5.0)
        return AgentResult(question=question, answer="There are 3000 students.", steps=[step],
                           final_sql=SQL, columns=["n"], rows=[{"n": 3000}], llm_calls=2)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    fake = FakeAgent()
    monkeypatch.setattr(api, "_build_agent", lambda: fake)
    with TestClient(api.app) as test_client:
        test_client.fake_agent = fake
        yield test_client


def test_ask_returns_answer_sql_and_steps(client) -> None:
    response = client.post("/ask", json={"question": "How many students?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "There are 3000 students."
    assert body["sql"] == SQL
    assert body["tables"] == ["dbo.students"]
    assert body["rows"] == [{"n": 3000}]
    assert body["steps"][0] == {"tool": "execute_readonly_sql", "args": {"query": SQL},
                                "ok": True, "summary": "1 row(s)", "duration_ms": 5.0}


def test_empty_question_is_rejected(client) -> None:
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_conversation_passes_history(client) -> None:
    conversation_id = client.post("/conversations").json()["conversation_id"]

    client.post(f"/conversations/{conversation_id}/ask", json={"question": "Participation in 2026?"})
    client.post(f"/conversations/{conversation_id}/ask", json={"question": "What about Coimbatore?"})

    assert client.fake_agent.histories[1][0].question == "Participation in 2026?"


def test_unknown_conversation_is_404(client) -> None:
    response = client.post("/conversations/nope/ask", json={"question": "hi"})
    assert response.status_code == 404


def test_validate_blocks_delete(client) -> None:
    body = client.post("/sql/validate", json={"sql": "DELETE FROM dbo.Students"}).json()
    assert body["is_valid"] is False


def test_swagger_lists_sample_questions(client) -> None:
    spec = client.get("/openapi.json").json()
    examples = spec["paths"]["/ask"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert "injection" in examples
