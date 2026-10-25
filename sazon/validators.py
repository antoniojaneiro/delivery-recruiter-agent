import re
from dataclasses import dataclass
from typing import Any

_NAME_WORD = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*$")


@dataclass(frozen=True)
class Validation:
    ok: bool
    value: Any = None
    reason: str = ""


def validate_name(raw: str) -> Validation:
    words = raw.split()
    if len(words) < 2:
        return Validation(False, reason="need first and last name")
    if not all(_NAME_WORD.match(w) for w in words):
        return Validation(False, reason="letters, hyphens and apostrophes only")
    return Validation(True, " ".join(words))
