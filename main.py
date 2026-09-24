import sys

from datapilot.config import ConfigError, get_settings
from datapilot.database import DatabaseError, run_query
from datapilot.gemini_client import GeminiError
from datapilot.question_analyzer import analyze_question

TEST_QUESTIONS = [
    "How many students from Coimbatore participated in 2026?",
    "Hello!",
    "Compare 2025 and 2026 results",
    "Show me the data",
]


def check_database() -> None:
    row = run_query("SELECT @@SERVERNAME AS server, DB_NAME() AS db, SYSTEM_USER AS login")[0]
    print(f"Database: connected to {row['server']} -- {row['db']} as {row['login']}")


def main() -> None:
    try:
        settings = get_settings()
        print(f"Starting {settings.app_name}")
        print(f"Using model: {settings.gemini_model}")

        check_database()

        for question in TEST_QUESTIONS:
            analysis = analyze_question(question)
            print(f"\nQ: {question}")
            print(analysis.model_dump_json(indent=2))
    except (ConfigError, DatabaseError, GeminiError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
