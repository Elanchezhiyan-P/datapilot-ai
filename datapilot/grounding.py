"""Hallucination check: every number in an answer must come from somewhere real.

An answer number is "grounded" if it matches, after rounding to the answer's own
precision, a number found in a tool result, the question or earlier conversation.
This catches invented and miscalculated numbers. It cannot catch a wrong query
whose (real) numbers are faithfully reported; that is what evaluation is for.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

# A number not glued to letters: matches "409", "1,398", "65.13"; skips "1st", "Q3".
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")


def extract_numbers(text: str) -> list[str]:
    return [match.replace(",", "") for match in _NUMBER.findall(text)]


def _numbers_in(value: Any) -> Iterable[Decimal]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float, Decimal)):
        yield Decimal(str(value))
    elif isinstance(value, str):
        for number in extract_numbers(value):
            yield Decimal(number)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _numbers_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _numbers_in(item)


def _matches(answer_number: str, known: set[Decimal]) -> bool:
    try:
        target = Decimal(answer_number)
    except InvalidOperation:
        return True
    places = -target.as_tuple().exponent if "." in answer_number else 0
    quantum = Decimal(1).scaleb(-places)
    return any(value.quantize(quantum) == target for value in known)


def ungrounded_numbers(answer: str, sources: Iterable[Any]) -> list[str]:
    """Numbers in `answer` that do not appear in any of `sources`."""
    known = {number for source in sources for number in _numbers_in(source)}
    return [number for number in dict.fromkeys(extract_numbers(answer))
            if not _matches(number, known)]
