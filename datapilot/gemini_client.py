from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from datapilot.config import get_settings

T = TypeVar("T", bound=BaseModel)


class GeminiError(Exception):
    """Raised when Gemini cannot produce an answer."""


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def _generate_text(
    contents: str,
    response_schema: type[BaseModel] | None = None,
    system_instruction: str | None = None,
) -> str:
    settings = get_settings()

    config = types.GenerateContentConfig(
        temperature=settings.gemini_temperature,
        system_instruction=system_instruction,
        # We call tools ourselves (Milestone 8); stop the SDK doing it implicitly.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    if response_schema is not None:
        config.response_mime_type = "application/json"
        config.response_schema = response_schema

    try:
        response = _get_client().models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=config,
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


def ask(question: str) -> str:
    return _generate_text(question)


def count_tokens(text: str) -> int:
    settings = get_settings()

    try:
        response = _get_client().models.count_tokens(
            model=settings.gemini_model, contents=text
        )
    except errors.APIError as e:
        raise GeminiError(
            f"Gemini token count failed (HTTP {e.code} {e.status}): {e.message}"
        ) from e

    return response.total_tokens or 0


def ask_structured(
    prompt: str, schema: type[T], system_instruction: str | None = None
) -> T:
    text = _generate_text(
        prompt, response_schema=schema, system_instruction=system_instruction
    )

    try:
        return schema.model_validate_json(text)
    except ValidationError as e:
        raise GeminiError(
            f"Gemini response did not match {schema.__name__}: {e}"
        ) from e
