import sys

from datapilot.config import ConfigError
from datapilot.database import DatabaseError
from datapilot.gemini_client import GeminiError, count_tokens
from datapilot.schema import discover_schema, format_schema_for_prompt


def main() -> None:
    try:
        schema = discover_schema()
        prompt_text = format_schema_for_prompt(schema)

        print(f"Database: {schema.database_name}")
        print(f"Tables:   {len(schema.tables)}\n")
        print(prompt_text)

        print(f"\nPrompt size: {len(prompt_text)} characters, "
              f"{count_tokens(prompt_text)} tokens (counted by Gemini)")
    except (ConfigError, DatabaseError, GeminiError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
