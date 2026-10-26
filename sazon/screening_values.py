"""Pure helpers of the screening: (de)serialising saved values and a pending change."""
from datetime import date

from sazon.spec import ScreeningSpec


def dump_change(pending) -> list | None:
    if pending is None:
        return None
    field, candidate, old_text, new_text = pending
    if isinstance(candidate, date):
        candidate = candidate.isoformat()
    elif isinstance(candidate, tuple):
        candidate = list(candidate)
    return [str(field), candidate, old_text, new_text]


def load_change(spec: ScreeningSpec, raw) -> tuple | None:
    if not raw:
        return None
    field, candidate, old_text, new_text = raw
    decode = spec.field(field).decode_candidate
    return field, decode(candidate) if decode else candidate, old_text, new_text


def load_value(spec: ScreeningSpec, key: str, value):
    """A saved answer read back from JSON. A key the spec no longer has is kept as it was saved."""
    try:
        decode = spec.field(key).decode_value
    except ValueError:
        return value
    return decode(value) if decode else value
