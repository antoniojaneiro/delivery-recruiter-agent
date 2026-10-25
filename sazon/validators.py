import difflib
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
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


def validate_license(value: bool | None) -> Validation:
    if not isinstance(value, bool):
        return Validation(False, reason="need a clear yes or no")
    return Validation(True, value)


@dataclass(frozen=True)
class CityMatch:
    status: CityMatchStatus
    city: str | None = None


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


# A country or state written after the place ("Madrid, España") is dropped; any other suffix is kept.
_PLACE_QUALIFIERS = ("espana", "spain", "mexico", "jalisco", "nuevo leon", "comunidad de madrid", "cataluna",
                     "catalunya", "comunitat valenciana", "estado de mexico", "edomex")


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text)).split())


def match_city(raw: str, areas: dict[str, list[str]]) -> CityMatch:
    names = {}
    for city, aliases in areas.items():
        for label in [city, *aliases]:
            names[_plain(label)] = city
    key = _plain(raw)
    if key in names:
        return CityMatch(CityMatchStatus.MATCH, names[key])
    for qualifier in sorted(_PLACE_QUALIFIERS, key=len, reverse=True):
        if key.endswith(" " + qualifier):
            key = key[: -len(qualifier) - 1]
            if key in names:
                return CityMatch(CityMatchStatus.MATCH, names[key])
            break
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.8)
    if close:
        return CityMatch(CityMatchStatus.CONFIRM, names[close[0]])
    return CityMatch(CityMatchStatus.OUT_OF_AREA)


AVAILABILITY = ("full_time", "part_time", "weekends")
SCHEDULES = ("morning", "afternoon", "evening", "flexible")


def validate_availability(values: list[str]) -> Validation:
    if not isinstance(values, (list, tuple)) or not values or any(v not in AVAILABILITY for v in values):
        return Validation(False, reason="pick full-time, part-time or weekends")
    return Validation(True, list(dict.fromkeys(values)))


def validate_schedule(value: str) -> Validation:
    if not isinstance(value, str) or value not in SCHEDULES:
        return Validation(False, reason="pick morning, afternoon, evening or flexible")
    return Validation(True, value)


KNOWN_PLATFORMS = ("glovo", "uber eats", "just eat", "rappi", "didi food")


MAX_YEARS = 60


def validate_experience(years: float | None, platforms: list[str]) -> Validation:
    if (isinstance(years, bool) or not isinstance(years, (int, float)) or not math.isfinite(years)
            or years < 0 or years > MAX_YEARS):
        return Validation(False, reason="need years of experience, 0 if none")
    if not isinstance(platforms, (list, tuple)) or not all(isinstance(p, str) for p in platforms):
        return Validation(False, reason="need the delivery platform")
    if years > 0 and not platforms:
        return Validation(False, reason="need the delivery platform")
    cleaned = [fold(p) for p in platforms]
    normalised = [p if p in KNOWN_PLATFORMS else "other" for p in cleaned]
    return Validation(True, {"years": years, "platforms": list(dict.fromkeys(normalised))})


MAX_START_WEEKS = 12


def validate_start_date(value: date | None, today: date) -> Validation:
    if not isinstance(value, date):
        return Validation(False, reason="need a date or a rough timeframe")
    if value < today:
        return Validation(False, reason="date is in the past")
    far = value > today + timedelta(weeks=MAX_START_WEEKS)
    return Validation(True, value, flags=("START_DATE_FAR",) if far else ())
