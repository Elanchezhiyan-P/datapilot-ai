from typing import Literal

from pydantic import BaseModel, Field

from datapilot.gemini_client import ask_structured


class QuestionAnalysis(BaseModel):
    intent: Literal["count", "list", "aggregate", "compare", "trend", "other"] = Field(
        description=(
            "What kind of answer the user wants. "
            "count = how many; list = show records; "
            "aggregate = sum, average, min or max; "
            "compare = two or more groups or periods side by side; "
            "trend = change over time; "
            "other = anything else, including greetings."
        )
    )
    entities: list[str] = Field(
        description=(
            "Things, places or groups mentioned in the question, "
            "e.g. 'students', 'Coimbatore'. "
            "Use only what the question mentions. Empty list if none."
        )
    )
    time_period: str | None = Field(
        description=(
            "The time period mentioned, e.g. '2026' or 'March 2025'. "
            "null if no time period is mentioned."
        )
    )
    needs_database: bool = Field(
        description=(
            "true if answering requires querying the organisation's data; "
            "false for greetings or general-knowledge questions."
        )
    )


_PROMPT = """You analyze questions that users ask a data-reporting assistant.
Do not answer the question. Only describe it.

Question: {question}"""


def analyze_question(question: str) -> QuestionAnalysis:
    return ask_structured(_PROMPT.format(question=question), QuestionAnalysis)
