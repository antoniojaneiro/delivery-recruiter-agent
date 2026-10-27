from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date

from screener import validators
from screener.consent import ConsentReading, is_hesitation, is_resume_request, read_consent
from screener.extraction import ControlFlags
from screener.model import CONSENT, NO_CONSENT, AreaMatchStatus, EventType, Language, Outcome, Status
from screener.language import language_of
from screener.directive import Directive, Kind
from screener.phrasing import consent_text_hash
from screener.screening_changes import propose_change
from screener.screening_precedence import Waiting, directive_for
from screener.screening_state import STATE_FIELDS, jsonable_values
from screener.spec import MISSING as _MISSING, ScreeningSpec

MAX_FOLLOW_UPS = 5
MAX_OFF_TOPIC = 3  # in total, not in a row (D55)
MAX_CITY_LENGTH = 80


LIVE = (Outcome.IN_PROGRESS, Outcome.BLOCKED)  # the chat is still open


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
    asking: str | None
    awaiting_confirmation: str | None
    awaiting_rejection: str | None
    previous_answer: str | None


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reasons: list[str]
    flags: list[str]


class Screening:
    def __init__(self, areas: dict[str, list[str]], spec: ScreeningSpec):
        self.areas = areas
        self.spec = spec
        for f in STATE_FIELDS:
            setattr(self, f.attribute, f.default(spec))
        self.version: int | None = None  # the stored version this copy was loaded at (None: a new candidate)

    @property
    def awaiting_confirmation(self) -> str | None:
        return self._pending_area[0] if self._pending_area else None

    def _hear_language(self, language: Language | None) -> None:
        """The candidate's language, when the client has wording for it."""
        if language and language in self.spec.pack.consent:
            self.language = language

    def record_consent(self, given: bool) -> None:
        self.consent = given
        self.events.append((EventType.CONSENT_GIVEN if given else EventType.CONSENT_DECLINED,
                            f"text_sha256={consent_text_hash(self.spec)}"))

    @property
    def awaiting_rejection(self) -> str | None:
        return self._pending_reject[0] if self._pending_reject else None

    @property
    def rejection_subject(self) -> str | None:
        """The candidate's own city text when a city rejection awaits confirmation."""
        if self._pending_reject and self._pending_reject[0] == self.spec.area_field:
            return str(self._pending_reject[1])
        return None

    def confirm_rejection(self, yes: bool) -> SubmitResult:
        if self._pending_reject is None:
            return SubmitResult(Status.FOLLOW_UP, "nothing is waiting for confirmation")
        field, raw = self._pending_reject
        self._pending_reject = None
        if not yes:
            return SubmitResult(Status.OK)
        if field == self.spec.area_field:
            self.out_of_area = True
        self.values[field] = raw
        self.events.append((EventType.FIELD_ACCEPTED, str(field)))
        return SubmitResult(Status.OK)

    # -- a changed answer is confirmed first (D54) ---------------------------

    @property
    def awaiting_change(self) -> bool:
        return self._pending_change is not None

    def drop_change(self) -> None:
        self._pending_change = None

    def resolve_change(self, yes: bool, today: date) -> Directive:
        """The candidate's yes or no to "Antes me dijiste X. ¿Lo cambio a Y?" (D54)."""
        field, candidate, _, _ = self._pending_change
        self._pending_change = None
        notice: tuple[str, ...] = ("kept",)
        if yes:
            self.events.append((EventType.FIELD_CHANGED, str(field)))
            result = self.submit(field, candidate, today)  # the usual flows (typo, outside the area, a rejecting answer) still apply
            notice = ("changed",) if result.status == Status.OK else ()  # else another question follows
        directive = self._directive_now(None)
        return replace(directive, notices=notice) if directive.kind != Kind.CLOSE else directive

    def _consider_change(self, field: str, candidate: object, today: date) -> None:
        if self._pending_change is None:  # one question at a time
            self._pending_change = propose_change(self.spec, self.areas, self.language, field, self.values[field],
                                                  candidate, today)

    # -- the offer of call slots (D48) ---------------------------------------

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

    def previous_answer(self, field: str | None) -> str | None:
        return self._previous.get(field)

    @property
    def is_open(self) -> bool:
        return self.decide().outcome in LIVE

    @property
    def needs_consent(self) -> bool:
        return self.consent is None

    def missing_fields(self) -> list[str]:
        return [f for f in self.spec.keys if f not in self.values]

    def close_directive(self) -> Directive:
        decision = self.decide()
        return Directive(Kind.CLOSE, outcome=decision.outcome, reasons=decision.reasons)

    def extraction_context(self) -> ExtractionContext:
        asking = self.next_field()
        return ExtractionContext(asking, self.awaiting_confirmation, self.awaiting_rejection,
                                 self.previous_answer(asking))

    def apply_consent_reply(self, reading: ConsentReading) -> Directive | None:
        """Nothing the candidate wrote with the answer is used (D44). None re-asks the question."""
        self._hear_language(reading.language)
        if reading.answer is None:
            return None
        self.record_consent(reading.answer)
        if not reading.answer:
            return self.close_directive()
        return Directive(Kind.ASK, field=self.next_field())

    def returning(self, message: str) -> Directive | None:
        """A candidate coming back to a closed chat (D56). Only two closes can be undone by the candidate:
        withdrawing (they must ask to continue) and declining consent (a later yes). None: not applicable."""
        if self.consent is False:
            reading = read_consent(message)
            if reading.answer is not True and not is_resume_request(message):
                return self.close_directive()
            self._hear_language(reading.language)
            self.record_consent(True)
            return Directive(Kind.ASK, field=self.next_field())
        if self.withdrawn:
            if not is_resume_request(message):
                return self.close_directive()
            self.withdrawn = False
            self.events.append((EventType.RESUMED, ""))
            if self.next_field() is None:  # everything was already collected: back to where they were
                return self.close_directive()
            return Directive(Kind.ASK, field=self.next_field())
        return None

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

    def apply(self, ex: ControlFlags, message: str, today: date) -> Directive:
        """Takes in what the candidate said and returns what to say next."""
        if ex.off_topic and (is_hesitation(message) or ex.wants_human or ex.asks_pay):
            # "mmm" did not answer, and a request for a person or a question about pay is never a strike
            ex = ex.model_copy(update={"off_topic": False})
        strikes = self._off_topic
        directive = self._next_directive(ex, message, today)
        notice = self._notice(ex, struck=self._off_topic > strikes)
        if notice and directive.kind != Kind.CLOSE:
            directive = replace(directive, notices=notice)
        return directive

    def _notice(self, ex: ControlFlags, struck: bool = False) -> tuple[str, ...]:
        """A request for a person or a question about pay gets a fixed answer before the next question."""
        names = []
        if ex.wants_human:
            names.append("human")
        if ex.asks_pay:
            self.events.append((EventType.PAY_QUESTION, ""))
            names.append("pay")
        if struck:
            names.append("offtopic")
        return tuple(names)

    def _next_directive(self, ex: ControlFlags, message: str, today: date) -> Directive:
        asking = self.next_field()
        self._hear_language(language_of(message, ex.language, self.language))
        if ex.wants_human:
            self.human_requested()
        if ex.withdraw:
            self.withdraw()
            return self.close_directive()
        unclear = self._apply_facts(ex, message, asking, today)
        return self._directive_now(unclear)

    def _directive_now(self, unclear: tuple[str, str] | None) -> Directive:
        waiting = Waiting(self.is_open, self.awaiting_rejection, self.rejection_subject, self.awaiting_confirmation,
                          self._pending_change, self.blocked_on, self.next_field())
        return directive_for(waiting, unclear, self.close_directive())

    def _apply_facts(self, ex: ControlFlags, message: str, asking: str | None,
                     today: date) -> tuple[str, str] | None:
        unclear = None
        answered = False

        def note(field: str, result: SubmitResult) -> None:
            nonlocal unclear, answered
            answered = True
            if result.status == Status.FOLLOW_UP and unclear is None:
                unclear = (field, result.reason)

        if self.awaiting_confirmation and ex.confirms_city is not None:
            note(self.spec.area_field, self.confirm_area(ex.confirms_city))
        if self.awaiting_rejection and ex.confirms_rejection is not None:
            note(self.awaiting_rejection, self.confirm_rejection(ex.confirms_rejection))
        for field in self.spec.keys:
            spec = self.spec.field(field)
            if field in self.values:  # already accepted: a different value is a change to confirm (D54)
                candidate = spec.read(ex, today, self.values[field])
                if candidate is not _MISSING and not (self.awaiting_confirmation or self.awaiting_rejection):
                    answered = True
                    self._consider_change(field, candidate, today)
                continue
            value = spec.read(ex, today, self._partial.get(field))
            if value is not _MISSING:
                result = self.submit(field, value, today, raw=message)
                if result.status == Status.FOLLOW_UP and spec.partial:
                    self._partial[field] = spec.partial(value)
                note(field, result)
        if not answered:
            if ex.off_topic:
                self.off_topic()
            elif asking and not (ex.wants_human or ex.asks_pay):  # a question is not an unclear answer
                note(asking, self.submit(asking, None, today, raw=message))
        return unclear

    def extracted(self) -> dict:
        return jsonable_values(self.values)

    def to_state(self) -> dict:
        return {f.key: f.dump(getattr(self, f.attribute)) for f in STATE_FIELDS}

    @classmethod
    def from_state(cls, areas: dict[str, list[str]], state: dict, spec: ScreeningSpec) -> "Screening":
        s = cls(areas, spec)
        for f in STATE_FIELDS:  # every key is optional: a state saved by an older or newer version must still load
            if f.key in state:
                setattr(s, f.attribute, f.load(state[f.key], spec))
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
        # a question that was waiting for an answer must not swallow the answer after they come back
        self._pending_change = None
        self._pending_reject = None
        self._pending_area = None
        self.events.append((EventType.WITHDRAWN, ""))

    def human_requested(self) -> None:
        self.events.append((EventType.HUMAN_REQUESTED, ""))

    def decide(self) -> Decision:
        flags = sorted(f for fl in self.validation_flags.values() for f in fl)
        if self.consent is False:
            return Decision(Outcome.DISQUALIFIED, [NO_CONSENT], [])
        if self.withdrawn:
            return Decision(Outcome.WITHDRAWN, [], flags)
        if self._off_topic >= MAX_OFF_TOPIC:
            return Decision(Outcome.ENDED_OFF_TOPIC, [], flags)
        reasons = [rule.reason for rule in self.spec.rules if rule.applies(self)]
        if reasons:
            return Decision(Outcome.DISQUALIFIED, reasons, flags)
        if self.stalled:
            return Decision(Outcome.STALLED, [], flags)
        if self._missing_field() is not None:
            if self.blocked_on:
                return Decision(Outcome.BLOCKED, [f"BLOCKED_ON_{self.blocked_on.upper()}"], flags)
            return Decision(Outcome.IN_PROGRESS, [], flags)
        return Decision(Outcome.QUALIFIED, [], flags)

    def next_field(self) -> str | None:
        if self.decide().outcome not in LIVE:
            return None
        return self._missing_field()

    def _missing_field(self) -> str | None:
        if self.consent is None:
            return CONSENT
        return next((f for f in self.spec.keys if f not in self.values), None)

    def submit(self, field: str, value: object, today: date, raw: object = None) -> SubmitResult:
        spec = self.spec.field(field)
        if not self.consent:
            raise ConsentRequired
        rejecting = spec.rejects is not None and spec.rejects(value)
        if self._pending_reject and self._pending_reject[0] == field:
            if rejecting or (field == self.spec.area_field and isinstance(value, str)
                             and validators.match_area(value, self.areas, self.spec.place_qualifiers).status == AreaMatchStatus.OUT_OF_AREA):
                return self.confirm_rejection(True)
            self._pending_reject = None
        if rejecting:
            self._pending_reject = (field, value)
            return SubmitResult(Status.CONFIRM_REJECT)
        if field == self.spec.area_field:
            return self._submit_area(value)
        return self._settle(field, self._validate(field, value, today), value if raw is None else raw)

    def confirm_area(self, yes: bool) -> SubmitResult:
        if self._pending_area is None:
            return SubmitResult(Status.FOLLOW_UP, "no city is waiting for confirmation")
        city, raw = self._pending_area
        self._pending_area = None
        if yes:
            return self._settle(self.spec.area_field, validators.Validation(True, city), raw)
        return self._settle(self.spec.area_field, validators.Validation(False, reason="city not confirmed"), raw)

    def _submit_area(self, raw: object) -> SubmitResult:
        self._pending_area = None
        if not isinstance(raw, str):
            return self._settle(self.spec.area_field, validators.Validation(False, reason="need a city"), raw)
        raw = " ".join(raw.split())[:MAX_CITY_LENGTH]  # what is stored of a place outside the area stays short
        match = validators.match_area(raw, self.areas, self.spec.place_qualifiers)
        if match.status == AreaMatchStatus.CONFIRM:
            self._pending_area = (match.city, raw)
            return SubmitResult(Status.CONFIRM, suggestion=match.city)
        if match.status == AreaMatchStatus.OUT_OF_AREA:
            self._pending_reject = (self.spec.area_field, raw)
            return SubmitResult(Status.CONFIRM_REJECT)
        return self._settle(self.spec.area_field, validators.Validation(True, match.city), raw)

    def _validate(self, field: str, value: object, today: date) -> validators.Validation:
        return self.spec.field(field).validate(value, today)

    def _settle(self, field: str, result: validators.Validation, raw: object) -> SubmitResult:
        self.validation_flags.pop(field, None)
        if result.ok:
            if result.flags:
                self.validation_flags[field] = list(result.flags)
            if field == self.spec.area_field:
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
