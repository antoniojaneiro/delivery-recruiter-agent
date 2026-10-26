"""Everything a Screening remembers between messages, declared once (D63): its attribute, its key in the saved
JSON, its starting value and how it is written and read back. A state saved by an older or newer version loads."""
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from screener.model import Language
from screener.screening_changes import dump_change, load_change
from screener.spec import ScreeningSpec


def _same(value):
    return value


def _unchanged(raw, spec):
    return raw


def _text_or_none(value):
    return str(value) if value else None


def jsonable_values(values: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in values.items()}


def _load_values(raw, spec: ScreeningSpec) -> dict:
    """Saved answers read back from JSON. A key the spec no longer has is kept as it was saved."""
    out = {}
    for key, value in raw.items():
        try:
            decode = spec.field(key).decode_value
        except ValueError:
            decode = None
        out[key] = decode(value) if decode else value
    return out


@dataclass(frozen=True)
class StateField:
    attribute: str
    key: str
    default: Callable[[ScreeningSpec], Any]
    dump: Callable[[Any], Any] = _same
    load: Callable[[Any, ScreeningSpec], Any] = _unchanged


STATE_FIELDS = (
    StateField("consent", "consent", lambda spec: None),
    StateField("values", "values", lambda spec: {}, dump=jsonable_values, load=_load_values),
    StateField("blocked_on", "blocked_on", lambda spec: None, dump=_text_or_none,
               load=lambda raw, spec: raw if raw else None),
    StateField("_slot_offer", "slot_offer", lambda spec: [], dump=list, load=lambda raw, spec: list(raw)),
    StateField("_slots_done", "slots_done", lambda spec: False),
    StateField("_unclear_picks", "unclear_picks", lambda spec: 0),
    StateField("out_of_area", "out_of_area", lambda spec: False),
    StateField("withdrawn", "withdrawn", lambda spec: False),
    StateField("stalled", "stalled", lambda spec: False),
    StateField("reminder_sent", "reminder_sent", lambda spec: False),
    StateField("language", "language", lambda spec: spec.pack.default_language,
               load=lambda raw, spec: Language(raw)),
    StateField("validation_flags", "validation_flags", lambda spec: {},
               load=lambda raw, spec: {k: list(v) for k, v in raw.items()}),
    StateField("_partial", "partial", lambda spec: {}, load=lambda raw, spec: dict(raw)),
    StateField("_pending_reject", "pending_reject", lambda spec: None,
               dump=lambda v: list(v) if v else None, load=lambda raw, spec: (raw[0], raw[1]) if raw else None),
    StateField("_pending_change", "pending_change", lambda spec: None, dump=dump_change,
               load=lambda raw, spec: load_change(spec, raw)),
    StateField("_previous", "previous", lambda spec: {}, load=lambda raw, spec: dict(raw)),
    StateField("events", "events", lambda spec: [], dump=lambda v: [list(e) for e in v],
               load=lambda raw, spec: [tuple(e) for e in raw]),
    StateField("_events_synced", "events_synced", lambda spec: 0),
    StateField("_off_topic", "off_topic", lambda spec: 0),
    StateField("_follow_ups", "follow_ups", lambda spec: {}, load=lambda raw, spec: dict(raw)),
    StateField("_pending_city", "pending_city", lambda spec: None,
               dump=lambda v: list(v) if v else None, load=lambda raw, spec: tuple(raw) if raw else None),
)
