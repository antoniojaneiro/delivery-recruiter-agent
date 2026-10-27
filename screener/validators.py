import difflib
import re
from dataclasses import dataclass
from typing import Any

from screener.language import plain
from screener.model import AreaMatchStatus

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
class AreaMatch:
    status: AreaMatchStatus
    city: str | None = None


def match_area(raw: str, areas: dict[str, list[str]], qualifiers: tuple[str, ...] = ()) -> AreaMatch:
    """A country or state written after the place (\"Leeds, England\") is dropped if the client lists it as a qualifier."""
    names = {}
    for city, aliases in areas.items():
        for label in [city, *aliases]:
            names[plain(label)] = city
    key = plain(raw)
    if key in names:
        return AreaMatch(AreaMatchStatus.MATCH, names[key])
    for qualifier in sorted(qualifiers, key=len, reverse=True):
        if key.endswith(" " + qualifier):
            key = key[: -len(qualifier) - 1]
            if key in names:
                return AreaMatch(AreaMatchStatus.MATCH, names[key])
            break
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.8)
    if close:
        return AreaMatch(AreaMatchStatus.CONFIRM, names[close[0]])
    return AreaMatch(AreaMatchStatus.OUT_OF_AREA)
