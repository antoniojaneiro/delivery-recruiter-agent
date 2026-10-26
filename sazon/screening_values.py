"""Pure helpers of the screening: reading a field out of an extraction, comparing validated values, and
(de)serialising a pending change."""
from datetime import date

from sazon.extraction import Extraction
from sazon.model import Field

MISSING = object()


def value_of(ex: Extraction, field: Field, today: date) -> object:
    match field:
        case Field.NAME:
            return ex.name if ex.name is not None else MISSING
        case Field.AVAILABILITY:
            return ex.availability or MISSING
        case Field.SCHEDULE:
            return ex.schedule if ex.schedule is not None else MISSING
        case Field.START_DATE:
            return ex.start_date.resolve(today) if ex.start_date is not None else MISSING
        case Field.CITY:
            return ex.city if ex.city is not None else MISSING
        case Field.LICENSE:
            return ex.has_license if ex.has_license is not None else MISSING
    return MISSING


def dump_change(pending) -> list | None:
    if pending is None:
        return None
    field, candidate, old_text, new_text = pending
    if isinstance(candidate, date):
        candidate = candidate.isoformat()
    elif isinstance(candidate, tuple):
        candidate = list(candidate)
    return [str(field), candidate, old_text, new_text]


def load_change(raw) -> tuple | None:
    if not raw:
        return None
    field, candidate, old_text, new_text = raw
    field = Field(field)
    if field == Field.START_DATE and isinstance(candidate, str):
        candidate = date.fromisoformat(candidate)
    elif field == Field.EXPERIENCE:
        candidate = tuple(candidate)
    return field, candidate, old_text, new_text
