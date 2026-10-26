"""The checks on Grupo Sazón's own fields: licence, availability, schedule, experience and start date (D63)."""
import math
from datetime import date, timedelta

from screener.validators import Validation, fold


def validate_license(value: bool | None) -> Validation:
    if not isinstance(value, bool):
        return Validation(False, reason="need a clear yes or no")
    return Validation(True, value)


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
# The ways people write them: letters and digits only, no spaces or hyphens ("Uber-Eats" -> "ubereats").
_PLATFORM_ALIASES = {
    "uber": "uber eats", "ubereats": "uber eats", "ubereat": "uber eats", "justeat": "just eat",
    "justeats": "just eat", "glovoapp": "glovo", "didi": "didi food", "didifood": "didi food",
    "glovo": "glovo", "rappi": "rappi",
}


def _squash(text: str) -> str:
    return "".join(c for c in fold(text) if c.isalnum())


MAX_YEARS = 60


def validate_experience(years: float | None, platforms: list[str]) -> Validation:
    if (isinstance(years, bool) or not isinstance(years, (int, float)) or not math.isfinite(years)
            or years < 0 or years > MAX_YEARS):
        return Validation(False, reason="need years of experience, 0 if none")
    if not isinstance(platforms, (list, tuple)) or not all(isinstance(p, str) for p in platforms):
        return Validation(False, reason="need the delivery platform")
    if years > 0 and not platforms:
        return Validation(False, reason="need the delivery platform")
    cleaned = [_PLATFORM_ALIASES.get(_squash(p), fold(p)) for p in platforms]
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
