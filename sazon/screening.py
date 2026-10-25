from dataclasses import dataclass
from datetime import date

from sazon import validators

FIELD_ORDER = ("name", "experience", "availability", "schedule", "start_date", "city", "license")
MAX_FOLLOW_UPS = 3
ELIGIBILITY = {"license": "LICENSE_UNCLEAR", "city": "CITY_UNCLEAR"}


class ConsentRequired(Exception):
    pass


@dataclass(frozen=True)
class SubmitResult:
    status: str  # "ok", "follow_up", "confirm" or "review"
    reason: str = ""
    suggestion: str | None = None


@dataclass(frozen=True)
class Decision:
    outcome: str  # IN_PROGRESS, QUALIFIED, DISQUALIFIED or NEEDS_REVIEW
    reasons: list[str]
    flags: list[str]


class Screening:
    def __init__(self, areas: dict[str, list[str]]):
        self.areas = areas
        self.consent: bool | None = None
        self.values: dict[str, object] = {}
        self.review_fields: set[str] = set()
        self.out_of_area = False
        self._follow_ups: dict[str, int] = {}
        self._pending_city: tuple[str, str] | None = None

    def record_consent(self, given: bool) -> None:
        self.consent = given

    def decide(self) -> Decision:
        flags = [f"{f.upper()}_NEEDS_REVIEW" for f in FIELD_ORDER if f in self.review_fields and f not in ELIGIBILITY]
        if self.consent is False:
            return Decision("DISQUALIFIED", ["NO_CONSENT"], [])
        reasons = []
        if self.values.get("license") is False:
            reasons.append("NO_LICENSE")
        if self.out_of_area:
            reasons.append("OUT_OF_AREA")
        if reasons:
            return Decision("DISQUALIFIED", reasons, flags)
        unclear = [code for f, code in ELIGIBILITY.items() if f in self.review_fields]
        if unclear:
            return Decision("NEEDS_REVIEW", unclear, flags)
        if self.next_field() is not None:
            return Decision("IN_PROGRESS", [], flags)
        return Decision("QUALIFIED", [], flags)

    def next_field(self) -> str | None:
        if self.consent is None:
            return "consent"
        return next((f for f in FIELD_ORDER if f not in self.values), None)

    def submit(self, field: str, value: object, today: date) -> SubmitResult:
        if not self.consent:
            raise ConsentRequired
        if field == "city":
            return self._submit_city(value)
        return self._settle(field, self._validate(field, value, today), value)

    def confirm_city(self, yes: bool) -> SubmitResult:
        city, raw = self._pending_city
        self._pending_city = None
        if yes:
            return self._settle("city", validators.Validation(True, city), raw)
        return self._settle("city", validators.Validation(False, reason="city not confirmed"), raw)

    def _submit_city(self, raw: str) -> SubmitResult:
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
        if result.ok:
            self.values[field] = result.value
            self.review_fields.discard(field)
            self._follow_ups.pop(field, None)
            return SubmitResult("ok")
        asked = self._follow_ups.get(field, 0)
        if asked >= MAX_FOLLOW_UPS:
            self.values[field] = raw
            self.review_fields.add(field)
            return SubmitResult("review", result.reason)
        self._follow_ups[field] = asked + 1
        return SubmitResult("follow_up", result.reason)
