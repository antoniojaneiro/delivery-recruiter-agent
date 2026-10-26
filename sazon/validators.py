import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sazon.model import CityMatchStatus

MAX_NAME_LENGTH = 100
_NAME_WORD = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*\.?$")  # a trailing dot allows titles and initials


@dataclass(frozen=True)
class Validation:
    ok: bool
    value: Any = None
    reason: str = ""
    flags: tuple[str, ...] = ()


def validate_name(raw: str) -> Validation:
    if not isinstance(raw, str):
        return Validation(False, reason="need first and last name")
    words = raw.split()
    if len(" ".join(words)) > MAX_NAME_LENGTH:
        return Validation(False, reason="too long for a name")
    if len(words) < 2:
        return Validation(False, reason="need first and last name")
    if not all(_NAME_WORD.match(w) for w in words):
        return Validation(False, reason="letters, hyphens and apostrophes only")
    return Validation(True, " ".join(words))


@dataclass(frozen=True)
class CityMatch:
    status: CityMatchStatus
    city: str | None = None


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text)).split())


def match_city(raw: str, areas: dict[str, list[str]], qualifiers: tuple[str, ...] = ()) -> CityMatch:
    """A country or state written after the place (\"Leeds, England\") is dropped if the client lists it as a qualifier."""
    names = {}
    for city, aliases in areas.items():
        for label in [city, *aliases]:
            names[_plain(label)] = city
    key = _plain(raw)
    if key in names:
        return CityMatch(CityMatchStatus.MATCH, names[key])
    for qualifier in sorted(qualifiers, key=len, reverse=True):
        if key.endswith(" " + qualifier):
            key = key[: -len(qualifier) - 1]
            if key in names:
                return CityMatch(CityMatchStatus.MATCH, names[key])
            break
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.8)
    if close:
        return CityMatch(CityMatchStatus.CONFIRM, names[close[0]])
    return CityMatch(CityMatchStatus.OUT_OF_AREA)
