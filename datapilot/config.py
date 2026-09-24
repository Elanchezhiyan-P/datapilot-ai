from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

REQUIRED_SETTINGS = (
    "APP_NAME",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_TEMPERATURE",
    "DB_SERVER",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_DRIVER",
)

class ConfigError(Exception):
    """Raised when required settings are missing."""

@dataclass(frozen=True)
class Settings:
    app_name: str
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float
    db_server: str
    db_name: str
    db_user: str
    db_password: str
    db_driver: str
    db_trust_server_certificate: bool


def get_settings() -> Settings:
    load_dotenv(ENV_FILE)

    missing = [name for name in REQUIRED_SETTINGS if not os.getenv(name)]
    if missing:
        raise ConfigError(
            f"Missing required settings: {', '.join(missing)}. "
            "Copy .env.example to .env and fill it in."
        )

    try:
        gemini_temperature = float(os.environ["GEMINI_TEMPERATURE"])
    except ValueError as e:
        raise ConfigError(
            f"GEMINI_TEMPERATURE must be a number, got {os.environ['GEMINI_TEMPERATURE']!r}."
        ) from e

    return Settings(
        app_name=os.environ["APP_NAME"],
        gemini_api_key=os.environ["GEMINI_API_KEY"],
        gemini_model=os.environ["GEMINI_MODEL"],
        gemini_temperature=gemini_temperature,
        db_server=os.environ["DB_SERVER"],
        db_name=os.environ["DB_NAME"],
        db_user=os.environ["DB_USER"],
        db_password=os.environ["DB_PASSWORD"],
        db_driver=os.environ["DB_DRIVER"],
        db_trust_server_certificate=(
            os.getenv("DB_TRUST_SERVER_CERTIFICATE", "no").lower() == "yes"
        ),
    )
