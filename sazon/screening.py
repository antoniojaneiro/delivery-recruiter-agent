from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sazon import validators

FIELD_ORDER = ("name", "experience", "availability", "schedule", "start_date", "city", "license")
MAX_FOLLOW_UPS = 3
MAX_OFF_TOPIC = 2
STALL_AFTER = timedelta(hours=24)
UNCAPPED = ("license", "city")  # eligibility: keep asking until clear (D27)


def is_stalled(last_message_at: datetime, now: datetime) -> bool:
    return now - last_message_at >= STALL_AFTER


class ConsentRequired(Exception):
    pass


@dataclass(frozen=True)
class SubmitResult:
    status: str  # "ok", "follow_up", "confirm" or "review"
    reason: str = ""
    suggestion: str | None = None


@dataclass(frozen=True)
class Decision:
    outcome: str  # IN_PROGRESS, QUALIFIED, DISQUALIFIED, ENDED_OFF_TOPIC or WITHDRAWN
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
        self.events: list[tuple[str, str]] = []
        self._off_topic = 0
        self.validation_flags: dict[str, list[str]] = {}
        self._follow_ups: dict[str, int] = {}
        self._pending_city: tuple[str, str] | None = None

    def record_consent(self, given: bool) -> None:
        self.consent = given

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
            "validation_flags": self.validation_flags,
            "events": [list(e) for e in self.events],
            "off_topic": self._off_topic,
            "follow_ups": self._follow_ups,
            "pending_city": list(self._pending_city) if self._pending_city else None,
        }

    @classmethod
    def from_state(cls, areas: dict[str, list[str]], state: dict) -> "Screening":
        s = cls(areas)
        s.consent = state["consent"]
        s.values = dict(state["values"])
        if isinstance(s.values.get("start_date"), str):
            s.values["start_date"] = date.fromisoformat(s.values["start_date"])
        s.review_fields = set(state["review_fields"])
        s.out_of_area = state["out_of_area"]
        s.withdrawn = state.get("withdrawn", False)
        s.validation_flags = {k: list(v) for k, v in state.get("validation_flags", {}).items()}
        s.events = [tuple(e) for e in state["events"]]
        s._off_topic = state["off_topic"]
        s._follow_ups = dict(state["follow_ups"])
        s._pending_city = tuple(state["pending_city"]) if state["pending_city"] else None
        return s

    def off_topic(self) -> None:
        self._off_topic += 1
        self.events.append(("off_topic", ""))

    def withdraw(self) -> None:
        self.withdrawn = True
        self.events.append(("withdrawn", ""))

    def human_requested(self) -> None:
        self.events.append(("human_requested", ""))

    def decide(self) -> Decision:
        flags = [f"{f.upper()}_NEEDS_REVIEW" for f in FIELD_ORDER if f in self.review_fields]
        flags += sorted(f for fl in self.validation_flags.values() for f in fl)
        if self.consent is False:
            return Decision("DISQUALIFIED", ["NO_CONSENT"], [])
        if self.withdrawn:
            return Decision("WITHDRAWN", [], flags)
        if self._off_topic >= MAX_OFF_TOPIC:
            return Decision("ENDED_OFF_TOPIC", [], flags)
        reasons = []
        if self.values.get("license") is False:
            reasons.append("NO_LICENSE")
        if self.out_of_area:
            reasons.append("OUT_OF_AREA")
        if reasons:
            return Decision("DISQUALIFIED", reasons, flags)
        if self.next_field() is not None:
            return Decision("IN_PROGRESS", [], flags)
        return Decision("QUALIFIED", [], flags)

    def next_field(self) -> str | None:
        if self.consent is None:
            return "consent"
        if not self.consent or self.withdrawn:
            return None
        return next((f for f in FIELD_ORDER if f not in self.values), None)

    def submit(self, field: str, value: object, today: date) -> SubmitResult:
        if not self.consent:
            raise ConsentRequired
        if field == "city":
            return self._submit_city(value)
        return self._settle(field, self._validate(field, value, today), value)

    def confirm_city(self, yes: bool) -> SubmitResult:
        if self._pending_city is None:
            return SubmitResult("follow_up", "no city is waiting for confirmation")
        city, raw = self._pending_city
        self._pending_city = None
        if yes:
            return self._settle("city", validators.Validation(True, city), raw)
        return self._settle("city", validators.Validation(False, reason="city not confirmed"), raw)

    def _submit_city(self, raw: object) -> SubmitResult:
        self._pending_city = None
        if not isinstance(raw, str):
            return self._settle("city", validators.Validation(False, reason="need a city"), raw)
        match = validators.match_city(raw, self.areas)
        if match.status == "confirm":
            self._pending_city = (match.city, raw)
            return SubmitResult("confirm", suggestion=match.city)
        if match.status == "out_of_area":
            self.out_of_area = True
            self.values["city"] = raw
            return SubmitResult("ok")
        return self._settle("city", validators.Validation(True, match.city), raw)

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
            case "license":
                return validators.validate_license(value)
        raise ValueError(f"unknown field: {field}")

    def _settle(self, field: str, result: validators.Validation, raw: object) -> SubmitResult:
        self.validation_flags.pop(field, None)
        if result.ok:
            if result.flags:
                self.validation_flags[field] = list(result.flags)
            if field == "city":
                self.out_of_area = False
            self._off_topic = 0
            self.values[field] = result.value
            self.review_fields.discard(field)
            self._follow_ups.pop(field, None)
            return SubmitResult("ok")
        self._off_topic = 0
        asked = self._follow_ups.get(field, 0)
        if asked >= MAX_FOLLOW_UPS and field not in UNCAPPED:
            self.values[field] = raw
            self.review_fields.add(field)
            return SubmitResult("review", result.reason)
        self._follow_ups[field] = asked + 1
        return SubmitResult("follow_up", result.reason)
