import time
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from datapilot.config import get_settings

T = TypeVar("T", bound=BaseModel)

# Rate limits and temporary server errors are worth retrying; a 400 never is.
RETRYABLE_CODES = {429, 500, 503}
RETRY_DELAYS_SECONDS = (2, 4, 8, 16, 30)


class GeminiError(Exception):
    """Raised when Gemini cannot produce an answer."""


@dataclass
class Usage:
    """Running totals, so evaluation can report real token counts."""

    calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0

    def reset(self) -> None:
        self.calls = self.prompt_tokens = self.output_tokens = self.retries = 0


USAGE = Usage()


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def _generate_content(
    contents: str | list[types.Content], config: types.GenerateContentConfig
) -> types.GenerateContentResponse:
    settings = get_settings()

    for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
        try:
            response = _get_client().models.generate_content(
                model=settings.gemini_model, contents=contents, config=config
            )
            break
        except errors.APIError as e:
            if e.code in RETRYABLE_CODES and attempt < len(RETRY_DELAYS_SECONDS):
                USAGE.retries += 1
                time.sleep(RETRY_DELAYS_SECONDS[attempt])
                continue
            raise GeminiError(
                f"Gemini API request failed (HTTP {e.code} {e.status}): {e.message}"
            ) from e

    USAGE.calls += 1
    if response.usage_metadata:
        USAGE.prompt_tokens += response.usage_metadata.prompt_token_count or 0
        USAGE.output_tokens += response.usage_metadata.candidates_token_count or 0
    return response


def _base_config(system_instruction: str | None) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=get_settings().gemini_temperature,
        system_instruction=system_instruction,
        # We call tools ourselves (Milestone 8); stop the SDK doing it implicitly.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _generate_text(
    contents: str,
    response_schema: type[BaseModel] | None = None,
    system_instruction: str | None = None,
) -> str:
    config = _base_config(system_instruction)
    if response_schema is not None:
        config.response_mime_type = "application/json"
        config.response_schema = response_schema

    response = _generate_content(contents, config)

    if not response.text:
        finish_reason = (
            response.candidates[0].finish_reason if response.candidates else "unknown"
        )
        raise GeminiError(f"Gemini returned no text (finish reason: {finish_reason}).")

    return response.text


def ask(question: str, system_instruction: str | None = None) -> str:
    return _generate_text(question, system_instruction=system_instruction)


def generate_with_tools(
    contents: list[types.Content],
    tools: list[types.FunctionDeclaration],
    system_instruction: str,
) -> types.GenerateContentResponse:
    """One model turn. The caller runs any requested tools and calls again."""
    config = _base_config(system_instruction)
    config.tools = [types.Tool(function_declarations=tools)]
    return _generate_content(contents, config)


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
