from functools import lru_cache

from google import genai
from google.genai import errors

from datapilot.config import get_settings


class GeminiError(Exception):
    """Raised when Gemini cannot produce an answer."""


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def ask(question: str) -> str:
    settings = get_settings()

    try:
        response = _get_client().models.generate_content(
            model=settings.gemini_model,
            contents=question,
        )
    except errors.APIError as e:
        raise GeminiError(
            f"Gemini API request failed (HTTP {e.code} {e.status}): {e.message}"
        ) from e

    if not response.text:
        finish_reason = (
            response.candidates[0].finish_reason if response.candidates else "unknown"
        )
        raise GeminiError(f"Gemini returned no text (finish reason: {finish_reason}).")

    return response.text
