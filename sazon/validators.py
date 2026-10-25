import difflib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

_NAME_WORD = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*$")


@dataclass(frozen=True)
class Validation:
    ok: bool
    value: Any = None
    reason: str = ""
    flags: tuple[str, ...] = ()


def validate_name(raw: str) -> Validation:
    words = raw.split()
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


AVAILABILITY = ("full_time", "part_time", "weekends")
SCHEDULES = ("morning", "afternoon", "evening", "flexible")


def validate_availability(values: list[str]) -> Validation:
    if not values or any(v not in AVAILABILITY for v in values):
        return Validation(False, reason="pick full-time, part-time or weekends")
    return Validation(True, list(dict.fromkeys(values)))


def validate_schedule(value: str) -> Validation:
    if value not in SCHEDULES:
        return Validation(False, reason="pick morning, afternoon, evening or flexible")
    return Validation(True, value)


KNOWN_PLATFORMS = ("glovo", "uber eats", "just eat", "rappi", "didi food")


def validate_experience(years: float | None, platforms: list[str]) -> Validation:
    if years is None or years < 0:
        return Validation(False, reason="need years of experience, 0 if none")
    if years > 0 and not platforms:
        return Validation(False, reason="need the delivery platform")
    cleaned = [_fold(p) for p in platforms]
    normalised = [p if p in KNOWN_PLATFORMS else "other" for p in cleaned]
    return Validation(True, {"years": years, "platforms": list(dict.fromkeys(normalised))})


MAX_START_WEEKS = 12


def validate_start_date(value: date | None, today: date) -> Validation:
    if value is None:
        return Validation(False, reason="need a date or a rough timeframe")
    if value < today:
        return Validation(False, reason="date is in the past")
    far = value > today + timedelta(weeks=MAX_START_WEEKS)
    return Validation(True, value, flags=("START_DATE_FAR",) if far else ())
