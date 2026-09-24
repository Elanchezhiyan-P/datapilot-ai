import sys

from datapilot.config import ConfigError, get_settings
from datapilot.gemini_client import GeminiError, ask


def main() -> None:
    try:
        settings = get_settings()
        print(f"Starting {settings.app_name}")
        print(f"Using model: {settings.gemini_model}")

        answer = ask("In one sentence, what is SQL?")
    except (ConfigError, GeminiError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(answer)


if __name__ == "__main__":
    main()
