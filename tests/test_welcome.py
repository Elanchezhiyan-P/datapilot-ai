import pytest

from datapilot import welcome
from datapilot.gemini_client import GeminiError
from datapilot.schema import DatabaseSchema
from datapilot.welcome import TableCount, build_welcome, clean_name

COUNTS = [TableCount(table="dbo.Students", label="Students", rows=3000),
          TableCount(table="dbo.Schools", label="Schools", rows=40)]
EMPTY_SCHEMA = DatabaseSchema(database_name="Test", tables=[])


@pytest.fixture(autouse=True)
def fake_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(welcome, "table_counts", lambda schema: COUNTS)


def test_grounded_ai_greeting_is_used(monkeypatch) -> None:
    monkeypatch.setattr(welcome, "ask", lambda prompt, system_instruction:
                        "Hi Elan! The database has 3,000 students across 40 schools. What would you like to know?")
    result = build_welcome("Elan", EMPTY_SCHEMA, use_ai=True)

    assert result.greeting_source == "ai"
    assert result.greeting.startswith("Hi Elan")


def test_greeting_with_invented_number_falls_back_to_template(monkeypatch) -> None:
    monkeypatch.setattr(welcome, "ask", lambda prompt, system_instruction: "Hi Elan! We have 5,000 students.")
    result = build_welcome("Elan", EMPTY_SCHEMA, use_ai=True)

    assert result.greeting_source == "template"
    assert "3,000 students" in result.greeting


def test_gemini_failure_falls_back_to_template(monkeypatch) -> None:
    def failing(prompt, system_instruction):
        raise GeminiError("quota exceeded")

    monkeypatch.setattr(welcome, "ask", failing)
    assert build_welcome("Elan", EMPTY_SCHEMA, use_ai=True).greeting_source == "template"


def test_default_welcome_makes_no_gemini_call(monkeypatch) -> None:
    def must_not_be_called(prompt, system_instruction):
        raise AssertionError("Gemini was called")

    monkeypatch.setattr(welcome, "ask", must_not_be_called)
    result = build_welcome("Elan", EMPTY_SCHEMA)
    assert result.greeting_source == "template"
    assert result.greeting == ("Hi Elan, welcome to DataPilot. The exam database currently holds "
                               "3,000 students and 40 schools. Ask me anything about it.")


def test_name_is_cleaned() -> None:
    assert clean_name("  Elan \n\t P\x00  ") == "Elan P"
    assert len(clean_name("x" * 100)) == welcome.MAX_NAME_LENGTH
