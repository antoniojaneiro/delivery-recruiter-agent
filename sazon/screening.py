from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date

from sazon import validators
from sazon.consent import ConsentReading, is_hesitation
from sazon.extraction import Extraction
from sazon.model import CityMatchStatus, EventType, Field, Language, Outcome, Reason, Status
from sazon.phrasing import Directive, Kind, consent_text_hash

FIELD_ORDER = (Field.NAME, Field.EXPERIENCE, Field.AVAILABILITY, Field.SCHEDULE, Field.START_DATE,
               Field.CITY, Field.LICENSE)
MAX_FOLLOW_UPS = 5
MAX_OFF_TOPIC = 3  # in total, not in a row (D55)


LIVE = (Outcome.IN_PROGRESS, Outcome.BLOCKED)  # the chat is still open
_MISSING = object()


class ConsentRequired(Exception):
    pass


@dataclass(frozen=True)
class SubmitResult:
    status: Status
    reason: str = ""
    suggestion: str | None = None


@dataclass(frozen=True)
class ExtractionContext:
    """What the model needs to know to read the next message."""
    asking: Field | None
    awaiting_confirmation: str | None
    awaiting_rejection: Field | None
    previous_answer: str | None


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
        self.blocked_on: Field | None = None
        self._slot_offer: list[int] = []
        self._slots_done = False
        self._unclear_picks = 0
        self.out_of_area = False
        self.withdrawn = False
        self.stalled = False
        self.reminder_sent = False
        self.language = Language.ES
        self.events: list[tuple[str, str]] = []
        self._events_synced = 0
        self._off_topic = 0
        self.validation_flags: dict[str, list[str]] = {}
        self._partial: dict[str, dict] = {}
        self._previous: dict[str, str] = {}
        self._follow_ups: dict[str, int] = {}
        self._pending_city: tuple[str, str] | None = None
        self._pending_reject: tuple[Field, object] | None = None

    @property
    def awaiting_confirmation(self) -> str | None:
        return self._pending_city[0] if self._pending_city else None

    def record_consent(self, given: bool) -> None:
        self.consent = given
        self.events.append((EventType.CONSENT_GIVEN if given else EventType.CONSENT_DECLINED,
                            f"text_sha256={consent_text_hash()}"))

    @property
    def awaiting_rejection(self) -> Field | None:
        return self._pending_reject[0] if self._pending_reject else None

    @property
    def rejection_subject(self) -> str | None:
        """The candidate's own city text when a city rejection awaits confirmation."""
        if self._pending_reject and self._pending_reject[0] == Field.CITY:
            return str(self._pending_reject[1])
        return None

    def confirm_rejection(self, yes: bool) -> SubmitResult:
        if self._pending_reject is None:
            return SubmitResult(Status.FOLLOW_UP, "nothing is waiting for confirmation")
        field, raw = self._pending_reject
        self._pending_reject = None
        if not yes:
            return SubmitResult(Status.OK)
        if field == Field.CITY:
            self.out_of_area = True
            self.values[Field.CITY] = raw
        else:
            self.values[Field.LICENSE] = False
        self.events.append((EventType.FIELD_ACCEPTED, str(field)))
        return SubmitResult(Status.OK)

    def previous_answer(self, field: Field | None) -> str | None:
        return self._previous.get(field)

    @property
    def is_open(self) -> bool:
        return self.decide().outcome in LIVE

    @property
    def needs_consent(self) -> bool:
        return self.consent is None

    @property
    def slot_offer(self) -> list[int]:
        return list(self._slot_offer)

    @property
    def slots_resolved(self) -> bool:
        return self._slots_done

    @property
    def awaiting_slot_choice(self) -> bool:
        return bool(self._slot_offer) and not self._slots_done and self.decide().outcome == Outcome.QUALIFIED

    def offer_slots(self, slot_ids: list[int]) -> None:
        self._slot_offer = list(slot_ids)
        self.events.append((EventType.SLOTS_OFFERED, ",".join(str(i) for i in slot_ids)))

    def note_unclear_pick(self) -> int:
        """Counts a reply to the slot list that could not be read; returns how many so far."""
        self._unclear_picks += 1
        return self._unclear_picks

    def resolve_slots(self) -> None:
        """The offer is over: booked, declined, or nothing to offer."""
        self._slot_offer = []
        self._slots_done = True

    def missing_fields(self) -> list[Field]:
        return [f for f in FIELD_ORDER if f not in self.values]

    def close_directive(self) -> Directive:
        decision = self.decide()
        return Directive(Kind.CLOSE, outcome=decision.outcome, reasons=decision.reasons)

    def extraction_context(self) -> ExtractionContext:
        asking = self.next_field()
        return ExtractionContext(asking, self.awaiting_confirmation, self.awaiting_rejection,
                                 self.previous_answer(asking))

    def apply_consent_reply(self, reading: ConsentReading) -> Directive | None:
        """Nothing the candidate wrote with the answer is used (D44). None re-asks the question."""
        if reading.language:
            self.language = reading.language
        if reading.answer is None:
            return None
        self.record_consent(reading.answer)
        if not reading.answer:
            return self.close_directive()
        return Directive(Kind.ASK, field=self.next_field())

    def apply_stop_request(self) -> Directive:
        """The candidate asked to stop. Read in plain code, so opting out never depends on the model."""
        self.withdraw()
        return self.close_directive()

    def model_failed(self, kind: str) -> Directive:
        self.record_model_failure(kind)
        return Directive(Kind.TECHNICAL_ERROR)

    def on_silence(self) -> Directive | None:
        """24 hours without a reply: one reminder, then STALLED (D35, D38)."""
        if not self.is_open:
            return None
        if self.reminder_sent:
            self.mark_stalled()
            return None
        self.send_reminder()
        return Directive(Kind.REMINDER)

    def apply(self, ex: Extraction, message: str, today: date) -> Directive:
        """Takes in what the candidate said and returns what to say next."""
        if ex.off_topic and (is_hesitation(message) or ex.wants_human or ex.asks_pay):
            # "mmm" did not answer, and a request for a person or a question about pay is never a strike
            ex = ex.model_copy(update={"off_topic": False})
        strikes = self._off_topic
        directive = self._next_directive(ex, message, today)
        notice = self._notice(ex, struck=self._off_topic > strikes)
        if notice and directive.kind != Kind.CLOSE:
            directive = replace(directive, notice=notice)
        return directive

    def _notice(self, ex: Extraction, struck: bool = False) -> str | None:
        """A request for a person or a question about pay gets a fixed answer before the next question."""
        names = []
        if ex.wants_human:
            names.append("human")
        if ex.asks_pay:
            self.events.append((EventType.PAY_QUESTION, ""))
            names.append("pay")
        if struck:
            names.append("offtopic")
        return "+".join(names) or None

    def _next_directive(self, ex: Extraction, message: str, today: date) -> Directive:
        asking = self.next_field()
        if ex.language:
            self.language = ex.language
        if ex.wants_human:
            self.human_requested()
        if ex.withdraw:
            self.withdraw()
            return self.close_directive()
        unclear = self._apply_facts(ex, message, asking, today)
        if not self.is_open:
            return self.close_directive()
        if self.awaiting_rejection:
            return Directive(Kind.CONFIRM_REJECTION, field=self.awaiting_rejection,
                             suggestion=self.rejection_subject)
        if self.awaiting_confirmation:
            return Directive(Kind.CONFIRM_CITY, suggestion=self.awaiting_confirmation)
        if self.blocked_on:
            return Directive(Kind.BLOCKED, field=self.blocked_on)
        if unclear:
            return Directive(Kind.FOLLOW_UP, field=unclear[0], reason=unclear[1])
        return Directive(Kind.ASK, field=self.next_field())

    def _apply_facts(self, ex: Extraction, message: str, asking: Field | None,
                     today: date) -> tuple[Field, str] | None:
        unclear = None
        answered = False

        def note(field: Field, result: SubmitResult) -> None:
            nonlocal unclear, answered
            answered = True
            if result.status == Status.FOLLOW_UP and unclear is None:
                unclear = (field, result.reason)

        if self.awaiting_confirmation and ex.confirms_city is not None:
            note(Field.CITY, self.confirm_city(ex.confirms_city))
        if self.awaiting_rejection and ex.confirms_rejection is not None:
            note(self.awaiting_rejection, self.confirm_rejection(ex.confirms_rejection))
        for field in FIELD_ORDER:
            if field == Field.EXPERIENCE:
                experience = self._experience(ex)
                if experience is not _MISSING:
                    result = self.submit(field, experience, today, raw=message)
                    if result.status == Status.FOLLOW_UP:
                        self._partial[field] = {"years": experience[0], "platforms": experience[1]}
                    note(field, result)
                continue
            value = _value(ex, field, today)
            if value is not _MISSING:
                note(field, self.submit(field, value, today, raw=message))
        if not answered:
            if ex.off_topic:
                self.off_topic()
            elif asking and not (ex.wants_human or ex.asks_pay):  # a question is not an unclear answer
                note(asking, self.submit(asking, None, today, raw=message))
        return unclear

    def _experience(self, ex: Extraction) -> object:
        if ex.experience_years is None and not ex.platforms:
            return _MISSING
        earlier = self._partial.get(Field.EXPERIENCE, {})
        years = ex.experience_years if ex.experience_years is not None else earlier.get("years")
        platforms = ex.platforms or earlier.get("platforms", [])
        return (years, platforms)

    def extracted(self) -> dict:
        return {
            k: v.isoformat() if isinstance(v, date) else v for k, v in self.values.items()
        }

    def to_state(self) -> dict:
        return {
            "consent": self.consent,
            "values": self.extracted(),
            "blocked_on": str(self.blocked_on) if self.blocked_on else None,
            "slot_offer": self._slot_offer,
            "slots_done": self._slots_done,
            "unclear_picks": self._unclear_picks,
            "out_of_area": self.out_of_area,
            "withdrawn": self.withdrawn,
            "stalled": self.stalled,
            "reminder_sent": self.reminder_sent,
            "language": self.language,
            "validation_flags": self.validation_flags,
            "partial": self._partial,
            "pending_reject": list(self._pending_reject) if self._pending_reject else None,
            "previous": self._previous,
            "events": [list(e) for e in self.events],
            "events_synced": self._events_synced,
            "off_topic": self._off_topic,
            "follow_ups": self._follow_ups,
            "pending_city": list(self._pending_city) if self._pending_city else None,
        }

    @classmethod
    def from_state(cls, areas: dict[str, list[str]], state: dict) -> "Screening":
        s = cls(areas)
        # Every key is optional: a state saved by an older or newer version must still load.
        s.consent = state.get("consent")
        s.values = dict(state.get("values", {}))
        if isinstance(s.values.get("start_date"), str):
            s.values["start_date"] = date.fromisoformat(s.values["start_date"])
        s.blocked_on = Field(state["blocked_on"]) if state.get("blocked_on") else None
        s._slot_offer = list(state.get("slot_offer", []))
        s._slots_done = state.get("slots_done", False)
        s._unclear_picks = state.get("unclear_picks", 0)
        s.out_of_area = state.get("out_of_area", False)
        s.withdrawn = state.get("withdrawn", False)
        s.stalled = state.get("stalled", False)
        s.reminder_sent = state.get("reminder_sent", False)
        s.language = Language(state.get("language", Language.ES))
        s.validation_flags = {k: list(v) for k, v in state.get("validation_flags", {}).items()}
        s._partial = dict(state.get("partial", {}))
        pending = state.get("pending_reject")
        s._pending_reject = (Field(pending[0]), pending[1]) if pending else None
        s._previous = dict(state.get("previous", {}))
        s.events = [tuple(e) for e in state.get("events", [])]
        s._events_synced = state.get("events_synced", 0)
        s._off_topic = state.get("off_topic", 0)
        s._follow_ups = dict(state.get("follow_ups", {}))
        pending_city = state.get("pending_city")
        s._pending_city = tuple(pending_city) if pending_city else None
        return s

    def off_topic(self) -> None:
        self._off_topic += 1
        self.events.append((EventType.OFF_TOPIC, ""))

    @contextmanager
    def syncing_events(self):
        """Yields the events not yet saved and counts them as saved, unless the block fails."""
        before = self._events_synced
        new = self.events[before:]
        self._events_synced = len(self.events)
        try:
            yield new
        except BaseException:
            self._events_synced = before
            raise

    def record_model_failure(self, kind: str) -> None:
        self.events.append((EventType.MODEL_FAILURE, kind))

    def send_reminder(self) -> None:
        self.reminder_sent = True
        self.events.append((EventType.REMINDER_SENT, ""))

    def mark_stalled(self) -> None:
        if self.decide().outcome in LIVE:
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
        flags = sorted(f for fl in self.validation_flags.values() for f in fl)
        if self.consent is False:
            return Decision(Outcome.DISQUALIFIED, [Reason.NO_CONSENT], [])
        if self.withdrawn:
            return Decision(Outcome.WITHDRAWN, [], flags)
        if self._off_topic >= MAX_OFF_TOPIC:
            return Decision(Outcome.ENDED_OFF_TOPIC, [], flags)
        reasons = []
        if self.values.get(Field.LICENSE) is False:
            reasons.append(Reason.NO_LICENSE)
        if self.out_of_area:
            reasons.append(Reason.OUT_OF_AREA)
        if reasons:
            return Decision(Outcome.DISQUALIFIED, reasons, flags)
        if self.stalled:
            return Decision(Outcome.STALLED, [], flags)
        if self._missing_field() is not None:
            if self.blocked_on:
                return Decision(Outcome.BLOCKED, [f"BLOCKED_ON_{self.blocked_on.upper()}"], flags)
            return Decision(Outcome.IN_PROGRESS, [], flags)
        return Decision(Outcome.QUALIFIED, [], flags)

    def next_field(self) -> Field | None:
        if self.decide().outcome not in LIVE:
            return None
        return self._missing_field()

    def _missing_field(self) -> Field | None:
        if self.consent is None:
            return Field.CONSENT
        return next((f for f in FIELD_ORDER if f not in self.values), None)

    def submit(self, field: str, value: object, today: date, raw: object = None) -> SubmitResult:
        if not self.consent:
            raise ConsentRequired
        if self._pending_reject and self._pending_reject[0] == field:
            if (field == Field.LICENSE and value is False) or (
                    field == Field.CITY and isinstance(value, str)
                    and validators.match_city(value, self.areas).status == CityMatchStatus.OUT_OF_AREA):
                return self.confirm_rejection(True)
            self._pending_reject = None
        if field == Field.LICENSE and value is False:
            self._pending_reject = (field, value)
            return SubmitResult(Status.CONFIRM_REJECT)
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
            self._pending_reject = (Field.CITY, raw)
            return SubmitResult(Status.CONFIRM_REJECT)
        return self._settle(Field.CITY, validators.Validation(True, match.city), raw)

    def _validate(self, field: str, value: object, today: date) -> validators.Validation:
        match field:
            case Field.NAME:
                return validators.validate_name(value)
            case Field.EXPERIENCE:
                if not isinstance(value, (tuple, list)) or len(value) != 2:
                    return validators.Validation(False, reason="need years and platform")
                return validators.validate_experience(*value)
            case Field.AVAILABILITY:
                return validators.validate_availability(value)
            case Field.SCHEDULE:
                return validators.validate_schedule(value)
            case Field.START_DATE:
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
            self.values[field] = result.value
            if self.blocked_on == field:
                self.blocked_on = None
            self._follow_ups.pop(field, None)
            self._previous.pop(field, None)
            self._partial.pop(field, None)
            self.events.append((EventType.FIELD_ACCEPTED, str(field)))
            return SubmitResult(Status.OK)
        asked = self._follow_ups.get(field, 0)
        if self.blocked_on == field:
            return SubmitResult(Status.BLOCKED, result.reason)
        if asked >= MAX_FOLLOW_UPS:
            if self.blocked_on is None:
                self.blocked_on = field
            self.events.append((EventType.BLOCKED, str(field)))
            return SubmitResult(Status.BLOCKED, result.reason)
        self._follow_ups[field] = asked + 1
        if isinstance(raw, str):
            self._previous[field] = raw
        self.events.append((EventType.FOLLOW_UP, f"{field}: {result.reason}"))
        return SubmitResult(Status.FOLLOW_UP, result.reason)


def _value(ex: Extraction, field: Field, today: date) -> object:
    match field:
        case Field.NAME:
            return ex.name if ex.name is not None else _MISSING
        case Field.AVAILABILITY:
            return ex.availability or _MISSING
        case Field.SCHEDULE:
            return ex.schedule if ex.schedule is not None else _MISSING
        case Field.START_DATE:
            return ex.start_date.resolve(today) if ex.start_date is not None else _MISSING
        case Field.CITY:
            return ex.city if ex.city is not None else _MISSING
        case Field.LICENSE:
            return ex.has_license if ex.has_license is not None else _MISSING
    return _MISSING
