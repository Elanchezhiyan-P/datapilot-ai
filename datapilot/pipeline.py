import time
from typing import Any, Literal

from pydantic import BaseModel

from datapilot.answer_generator import generate_answer
from datapilot.database import DatabaseError, run_readonly_query
from datapilot.gemini_client import GeminiError
from datapilot.schema import DatabaseSchema, discover_schema
from datapilot.sql_generator import generate_sql
from datapilot.sql_validator import validate_sql

MAX_ROWS = 500

Status = Literal["answered", "cannot_answer", "needs_clarification", "blocked", "error"]


class PipelineResult(BaseModel):
    """What happened for one question. Only artifacts, never model reasoning."""

    question: str
    status: Status
    answer: str
    sql: str | None = None
    tables: list[str] = []
    validation_errors: list[str] = []
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    truncated: bool = False
    timings_ms: dict[str, float] = {}


class _Timer:
    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}

    def measure(self, step: str, start: float) -> None:
        self.timings_ms[step] = round((time.perf_counter() - start) * 1000, 1)


def answer_question(question: str, schema: DatabaseSchema | None = None) -> PipelineResult:
    timer = _Timer()

    start = time.perf_counter()
    schema = schema or discover_schema()
    timer.measure("schema", start)

    # 1. Natural language -> SQL
    start = time.perf_counter()
    try:
        generation = generate_sql(question, schema)
    except GeminiError as e:
        return PipelineResult(question=question, status="error", answer=str(e),
                              timings_ms=timer.timings_ms)
    timer.measure("generate_sql", start)

    if not generation.can_answer or not generation.sql:
        status: Status = (
            "needs_clarification" if generation.clarification_needed else "cannot_answer"
        )
        answer = generation.clarification_needed or generation.explanation
        return PipelineResult(question=question, status=status, answer=answer,
                              timings_ms=timer.timings_ms)

    # 2. Validate: the model's SQL is untrusted input.
    start = time.perf_counter()
    validation = validate_sql(generation.sql, schema.table_names())
    timer.measure("validate", start)

    if not validation.is_valid:
        return PipelineResult(
            question=question,
            status="blocked",
            answer="The generated query was blocked by the safety checks.",
            sql=generation.sql,
            tables=validation.tables,
            validation_errors=validation.errors,
            timings_ms=timer.timings_ms,
        )

    # 3. Execute with the read-only login, row limit and query timeout.
    start = time.perf_counter()
    try:
        result = run_readonly_query(generation.sql, max_rows=MAX_ROWS)
    except DatabaseError as e:
        # Typically an invalid column or table name: a hallucination that got past the prompt.
        return PipelineResult(question=question, status="error",
                              answer=f"The query failed to run: {e}",
                              sql=generation.sql, tables=validation.tables,
                              timings_ms=timer.timings_ms)
    timer.measure("execute", start)

    # 4. Rows -> natural-language answer
    start = time.perf_counter()
    try:
        answer = generate_answer(question, result)
    except GeminiError as e:
        answer = f"The query ran, but the answer could not be written: {e}"
    timer.measure("generate_answer", start)

    return PipelineResult(
        question=question,
        status="answered",
        answer=answer,
        sql=generation.sql,
        tables=validation.tables,
        columns=result.columns,
        rows=result.rows,
        truncated=result.truncated,
        timings_ms=timer.timings_ms,
    )
