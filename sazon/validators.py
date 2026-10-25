import difflib
import re
import unicodedata
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


def validate_license(value: bool | None) -> Validation:
    if value is None:
        return Validation(False, reason="need a clear yes or no")
    return Validation(True, value)


@dataclass(frozen=True)
class CityMatch:
    status: str  # "match", "confirm" or "out_of_area"
    city: str | None = None


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def match_city(raw: str, areas: dict[str, list[str]]) -> CityMatch:
    names = {}
    for city, aliases in areas.items():
        for label in [city, *aliases]:
            names[_fold(label)] = city
    key = _fold(raw)
    if key in names:
        return CityMatch("match", names[key])
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.8)
    if close:
        return CityMatch("confirm", names[close[0]])
    return CityMatch("out_of_area")
