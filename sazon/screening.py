from dataclasses import dataclass
from datetime import date

from sazon import validators
from sazon.model import CityMatchStatus, EventType, Field, Outcome, Status

FIELD_ORDER = (Field.NAME, Field.EXPERIENCE, Field.AVAILABILITY, Field.SCHEDULE, Field.START_DATE,
               Field.CITY, Field.LICENSE)
MAX_FOLLOW_UPS = 3
MAX_OFF_TOPIC = 2
UNCAPPED = (Field.LICENSE, Field.CITY)  # eligibility: keep asking until clear (D27)


class ConsentRequired(Exception):
    pass


@dataclass(frozen=True)
class SubmitResult:
    status: Status
    reason: str = ""
    suggestion: str | None = None


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reasons: list[str]
    flags: list[str]


class Screening:
    def __init__(self, areas: dict[str, list[str]]):
        self.areas = areas
        self.consent: bool | None = None
        self.values: dict[str, object] = {}
        self.review_fields: set[str] = set()
        self.out_of_area = False
        self.withdrawn = False
        self.stalled = False
        self.reminder_sent = False
        self.language = "es"
        self.events: list[tuple[str, str]] = []
        self.events_synced = 0
        self._off_topic = 0
        self.validation_flags: dict[str, list[str]] = {}
        self.partial: dict[str, dict] = {}
        self._previous: dict[str, str] = {}
        self._follow_ups: dict[str, int] = {}
        self._pending_city: tuple[str, str] | None = None

    @property
    def awaiting_confirmation(self) -> str | None:
        return self._pending_city[0] if self._pending_city else None

    def record_consent(self, given: bool) -> None:
        self.consent = given
        self.events.append((EventType.CONSENT_GIVEN if given else EventType.CONSENT_DECLINED, ""))

    def previous_answer(self, field: Field | None) -> str | None:
        return self._previous.get(field)

    def extracted(self) -> dict:
        return {
            k: v.isoformat() if isinstance(v, date) else v for k, v in self.values.items()
        }

    def to_state(self) -> dict:
        return {
            "consent": self.consent,
            "values": self.extracted(),
            "review_fields": sorted(self.review_fields),
            "out_of_area": self.out_of_area,
            "withdrawn": self.withdrawn,
            "stalled": self.stalled,
            "reminder_sent": self.reminder_sent,
            "language": self.language,
            "validation_flags": self.validation_flags,
            "partial": self.partial,
            "previous": self._previous,
            "events": [list(e) for e in self.events],
            "events_synced": self.events_synced,
            "off_topic": self._off_topic,
            "follow_ups": self._follow_ups,
            "pending_city": list(self._pending_city) if self._pending_city else None,
        }

    @classmethod
    def from_state(cls, areas: dict[str, list[str]], state: dict) -> "Screening":
        s = cls(areas)
        s.consent = state["consent"]
        s.values = dict(state["values"])
        s.review_fields = set(state["review_fields"])
        if isinstance(s.values.get("start_date"), str) and Field.START_DATE not in s.review_fields:
            s.values["start_date"] = date.fromisoformat(s.values["start_date"])
        s.out_of_area = state["out_of_area"]
        s.withdrawn = state.get("withdrawn", False)
        s.stalled = state.get("stalled", False)
        s.reminder_sent = state.get("reminder_sent", False)
        s.language = state.get("language", "es")
        s.validation_flags = {k: list(v) for k, v in state.get("validation_flags", {}).items()}
        s.partial = dict(state.get("partial", {}))
        s._previous = dict(state.get("previous", {}))
        s.events = [tuple(e) for e in state["events"]]
        s.events_synced = state.get("events_synced", 0)
        s._off_topic = state["off_topic"]
        s._follow_ups = dict(state["follow_ups"])
        s._pending_city = tuple(state["pending_city"]) if state["pending_city"] else None
        return s

    def off_topic(self) -> None:
        self._off_topic += 1
        self.events.append((EventType.OFF_TOPIC, ""))

    def pending_events(self) -> list[tuple[str, str]]:
        return self.events[self.events_synced:]

    def mark_events_synced(self) -> None:
        self.events_synced = len(self.events)

    def record_model_failure(self, kind: str) -> None:
        self.events.append((EventType.MODEL_FAILURE, kind))

    def send_reminder(self) -> None:
        self.reminder_sent = True
        self.events.append((EventType.REMINDER_SENT, ""))

    def mark_stalled(self) -> None:
        if self.decide().outcome == Outcome.IN_PROGRESS:
            self.stalled = True

    def resume(self) -> None:
        self.reminder_sent = False
        if self.stalled:
            self.stalled = False
            self.events.append((EventType.RESUMED, ""))

    def withdraw(self) -> None:
        self.withdrawn = True
        self.events.append((EventType.WITHDRAWN, ""))

    def human_requested(self) -> None:
        self.events.append((EventType.HUMAN_REQUESTED, ""))

    def decide(self) -> Decision:
        flags = [f"{f.upper()}_NEEDS_REVIEW" for f in FIELD_ORDER if f in self.review_fields]
        flags += sorted(f for fl in self.validation_flags.values() for f in fl)
        if self.consent is False:
            return Decision(Outcome.DISQUALIFIED, ["NO_CONSENT"], [])
        if self.withdrawn:
            return Decision(Outcome.WITHDRAWN, [], flags)
        if self._off_topic >= MAX_OFF_TOPIC:
            return Decision(Outcome.ENDED_OFF_TOPIC, [], flags)
        reasons = []
        if self.values.get(Field.LICENSE) is False:
            reasons.append("NO_LICENSE")
        if self.out_of_area:
            reasons.append("OUT_OF_AREA")
        if reasons:
            return Decision(Outcome.DISQUALIFIED, reasons, flags)
        if self.stalled:
            return Decision(Outcome.STALLED, [], flags)
        if self._missing_field() is not None:
            return Decision(Outcome.IN_PROGRESS, [], flags)
        return Decision(Outcome.QUALIFIED, [], flags)

    def next_field(self) -> Field | None:
        if self.decide().outcome != Outcome.IN_PROGRESS:
            return None
        return self._missing_field()

    def _missing_field(self) -> Field | None:
        if self.consent is None:
            return Field.CONSENT
        return next((f for f in FIELD_ORDER if f not in self.values), None)

    def submit(self, field: str, value: object, today: date, raw: object = None) -> SubmitResult:
        if not self.consent:
            raise ConsentRequired
        if field == Field.CITY:
            return self._submit_city(value)
        return self._settle(field, self._validate(field, value, today), value if raw is None else raw)

    def confirm_city(self, yes: bool) -> SubmitResult:
        if self._pending_city is None:
            return SubmitResult(Status.FOLLOW_UP, "no city is waiting for confirmation")
        city, raw = self._pending_city
        self._pending_city = None
        if yes:
            return self._settle(Field.CITY, validators.Validation(True, city), raw)
        return self._settle(Field.CITY, validators.Validation(False, reason="city not confirmed"), raw)

    def _submit_city(self, raw: object) -> SubmitResult:
        self._pending_city = None
        if not isinstance(raw, str):
            return self._settle(Field.CITY, validators.Validation(False, reason="need a city"), raw)
        match = validators.match_city(raw, self.areas)
        if match.status == CityMatchStatus.CONFIRM:
            self._pending_city = (match.city, raw)
            return SubmitResult(Status.CONFIRM, suggestion=match.city)
        if match.status == CityMatchStatus.OUT_OF_AREA:
            self.out_of_area = True
            self.values[Field.CITY] = raw
            return SubmitResult(Status.OK)
        return self._settle(Field.CITY, validators.Validation(True, match.city), raw)

    def _validate(self, field: str, value: object, today: date) -> validators.Validation:
        match field:
            case "name":
                return validators.validate_name(value)
            case "experience":
                if not isinstance(value, (tuple, list)) or len(value) != 2:
                    return validators.Validation(False, reason="need years and platform")
                return validators.validate_experience(*value)
            case "availability":
                return validators.validate_availability(value)
            case "schedule":
                return validators.validate_schedule(value)
            case "start_date":
                return validators.validate_start_date(value, today)
            case Field.LICENSE:
                return validators.validate_license(value)
        raise ValueError(f"unknown field: {field}")

    def _settle(self, field: str, result: validators.Validation, raw: object) -> SubmitResult:
        self.validation_flags.pop(field, None)
        if result.ok:
            if result.flags:
                self.validation_flags[field] = list(result.flags)
            if field == Field.CITY:
                self.out_of_area = False
            self._off_topic = 0
            self.values[field] = result.value
            self.review_fields.discard(field)
            self._follow_ups.pop(field, None)
            self._previous.pop(field, None)
            self.partial.pop(field, None)
            self.events.append((EventType.FIELD_ACCEPTED, str(field)))
            return SubmitResult(Status.OK)
        self._off_topic = 0
        asked = self._follow_ups.get(field, 0)
        if asked >= MAX_FOLLOW_UPS and field not in UNCAPPED:
            self.values[field] = raw
            self.review_fields.add(field)
            self._previous.pop(field, None)
            self.partial.pop(field, None)
            self.events.append((EventType.REVIEW, str(field)))
            return SubmitResult(Status.REVIEW, result.reason)
        self._follow_ups[field] = asked + 1
        if isinstance(raw, str):
            self._previous[field] = raw
        self.events.append((EventType.FOLLOW_UP, f"{field}: {result.reason}"))
        return SubmitResult(Status.FOLLOW_UP, result.reason)
