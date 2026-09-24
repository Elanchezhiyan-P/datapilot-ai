"""Ask DataPilot a question and let Gemini choose the tools.

    python tools_ask.py "Which school had the highest average score in 2026?"
    python tools_ask.py            # interactive mode
"""
import json
import sys

from datapilot.config import ConfigError
from datapilot.database import DatabaseError
from datapilot.gemini_client import GeminiError
from datapilot.schema import DatabaseSchema, discover_schema
from datapilot.tool_calling import ToolRunResult, run_with_tools


def _short(value: object, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def print_result(result: ToolRunResult) -> None:
    print(f"\nQuestion: {result.question}")
    for number, call in enumerate(result.tool_calls, start=1):
        print(f"  [{number}] {call.name}({_short(call.args)})  {call.duration_ms:.0f} ms")
        print(f"      -> {_short(call.result)}")
    stopped = " (stopped at turn limit)" if result.stopped_early else ""
    print(f"Turns: {result.turns}{stopped}")
    print(f"\nAnswer: {result.answer}\n")


def run(question: str, schema: DatabaseSchema) -> None:
    try:
        print_result(run_with_tools(question, schema))
    except GeminiError as e:
        print(f"Error: {e}", file=sys.stderr)


def main() -> None:
    try:
        schema = discover_schema()

        if len(sys.argv) > 1:
            run(" ".join(sys.argv[1:]), schema)
            return

        print("DataPilot AI (tool calling). Empty line to quit.")
        while question := input("\n> ").strip():
            run(question, schema)
    except (ConfigError, DatabaseError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
