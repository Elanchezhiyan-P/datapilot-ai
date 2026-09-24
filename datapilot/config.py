from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

REQUIRED_SETTINGS = ("APP_NAME", "GEMINI_API_KEY", "GEMINI_MODEL")


class ConfigError(Exception):
    """Raised when required settings are missing."""


@dataclass(frozen=True)
class Settings:
    app_name: str
    gemini_api_key: str
    gemini_model: str


def get_settings() -> Settings:
    load_dotenv(ENV_FILE)

    missing = [name for name in REQUIRED_SETTINGS if not os.getenv(name)]
    if missing:
        raise ConfigError(
            f"Missing required settings: {', '.join(missing)}. "
            "Copy .env.example to .env and fill it in."
        )

    return Settings(
        app_name=os.environ["APP_NAME"],
        gemini_api_key=os.environ["GEMINI_API_KEY"],
        gemini_model=os.environ["GEMINI_MODEL"],
    )
