from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

# Gemini settings are not required at startup: the chat page can set them later
# (POST /setup/gemini). Anything that calls Gemini checks them at call time.
REQUIRED_SETTINGS = (
    "APP_NAME",
    "DB_SERVER",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_DRIVER",
)
DEFAULT_TEMPERATURE = "0.0"

class ConfigError(Exception):
    """Raised when required settings are missing."""

@dataclass(frozen=True)
class Settings:
    app_name: str
    gemini_api_key: str | None
    gemini_model: str | None
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

    temperature_text = os.getenv("GEMINI_TEMPERATURE") or DEFAULT_TEMPERATURE
    try:
        gemini_temperature = float(temperature_text)
    except ValueError as e:
        raise ConfigError(
            f"GEMINI_TEMPERATURE must be a number, got {temperature_text!r}."
        ) from e

    return Settings(
        app_name=os.environ["APP_NAME"],
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL") or None,
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


def set_values(values: dict[str, str], save_to_env_file: bool, env_file: Path = ENV_FILE) -> None:
    """Apply settings to this process and, optionally, write them into .env.

    Existing lines and comments in .env are kept; matching KEY= lines are replaced.
    """
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ConfigError(f"{key} must be a single line.")
        os.environ[key] = value

    if not save_to_env_file:
        return

    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    remaining = dict(values)
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in remaining:
            lines[index] = f"{key}={remaining.pop(key)}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
