"""D54: a changed answer is confirmed with the candidate before it replaces the saved one. This module decides
whether an answer is a change, and saves and loads the question that waits for the candidate's yes or no."""
from datetime import date

from screener import validators
from screener.model import Language
from screener.phrasing import describe_value, echo
from screener.spec import ScreeningSpec


def propose_change(spec: ScreeningSpec, areas: dict[str, list[str]], language: Language, field: str, old: object,
                   candidate: object, today: date) -> tuple | None:
    """(field, candidate, old answer in words, new answer in words) when `candidate` differs from the saved `old`
    answer and would be accepted; None when it is the same answer or would not be accepted anyway."""
    if field == spec.area_field:
        if not isinstance(candidate, str):
            return None
        match = validators.match_area(candidate, areas, spec.place_qualifiers)
        if match.city == old:
            return None  # the same city, however it is spelled (an outside-the-area city has no match)
        shown = match.city or echo(candidate)
    else:
        result = spec.field(field).validate(candidate, today)
        if not result.ok or spec.field(field).same(old, result.value):
            return None
        shown = result.value
    return field, candidate, describe_value(spec, field, old, language), describe_value(spec, field, shown, language)


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
