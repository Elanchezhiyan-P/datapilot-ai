"""Ask DataPilot a question.

    python ask.py "How many students are from Coimbatore?"
    python ask.py            # interactive mode
"""
import sys

from datapilot.config import ConfigError
from datapilot.database import DatabaseError
from datapilot.pipeline import PipelineResult, answer_question
from datapilot.schema import DatabaseSchema, discover_schema

PREVIEW_ROWS = 10


def print_result(result: PipelineResult) -> None:
    print(f"\nQuestion:   {result.question}")
    print(f"Status:     {result.status}")
    if result.tables:
        print(f"Tables:     {', '.join(result.tables)}")
    if result.sql:
        print(f"SQL:\n  {result.sql.strip()}")
    for error in result.validation_errors:
        print(f"Blocked:    {error}")

    if result.status == "answered":
        suffix = " (row limit reached, result truncated)" if result.truncated else ""
        print(f"Rows:       {len(result.rows)}{suffix}")
        for row in result.rows[:PREVIEW_ROWS]:
            print("  ", " | ".join(str(value) for value in row.values()))
        if len(result.rows) > PREVIEW_ROWS:
            print(f"   ... {len(result.rows) - PREVIEW_ROWS} more")

    timings = ", ".join(f"{step} {ms:.0f} ms" for step, ms in result.timings_ms.items())
    print(f"Timing:     {timings}")
    print(f"\nAnswer:     {result.answer}\n")


def run(question: str, schema: DatabaseSchema) -> None:
    print_result(answer_question(question, schema))


def main() -> None:
    try:
        schema = discover_schema()

        if len(sys.argv) > 1:
            run(" ".join(sys.argv[1:]), schema)
            return

        print("DataPilot AI. Ask your data. Empty line to quit.")
        while question := input("\n> ").strip():
            run(question, schema)
    except (ConfigError, DatabaseError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
