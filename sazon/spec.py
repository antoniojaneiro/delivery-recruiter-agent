"""What a client defines to use the screening engine (D63): its fields, the rules that end a screening and its
wording. Everything here is data and small functions; the engine owns the flow."""
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from operator import eq
from typing import Any, Callable

from sazon.extraction import build_model
from sazon.model import Language, Outcome, Reason
from sazon.pack import Pack, Text
from sazon.validators import Validation

MISSING = object()  # what a field's reader returns when the message says nothing about it


def read_attribute(name: str, empty_is_missing: bool = False) -> Callable[[Any, date, Any], object]:
    """A reader for a field that is one attribute of the model's reply."""
    def read(reply, today, base):
        value = getattr(reply, name)
        return MISSING if value is None or (empty_is_missing and not value) else value
    return read


@dataclass(frozen=True)
class FieldSpec:
    key: str
    ask: Text  # the question; also what the model is told to keep the meaning of when it rephrases
    what: Text  # "your first and last name": completes "I can't continue until you tell me ..."
    label: str  # the recruiter's name for the field
    validate: Callable[[Any, date], Validation] | None = None  # None: the engine's area matching decides
    same: Callable[[Any, Any], bool] = eq  # compares validated values, so the same answer is never a change
    rejects: Callable[[Any], bool] | None = None  # an answer that ends the screening once the candidate confirms it
    confirm_rejection: Text | None = None  # asked before a rejecting answer counts; {city} is the candidate's text
    read: Callable[[Any, date, Any], object] | None = None  # (reply, today, base) -> a value or MISSING
    # base: what was kept of an earlier unclear answer, or the saved value when a change is being read
    partial: Callable[[Any], dict] | None = None  # what to keep of an unclear answer to combine with the next
    schema: dict[str, tuple] = field(default_factory=dict)  # the attributes this field adds to the model's reply
    prompt: str = ""  # the lines describing those attributes to the model
    decode_value: Callable[[Any], Any] | None = None  # a saved value read back from JSON
    decode_candidate: Callable[[Any], Any] | None = None  # a pending change read back from JSON
    describe: Callable[[Any, Language], str] | None = None  # a value in the candidate's words, for a change question
    card: Callable[[Any], str] | None = None  # the line for the recruiter's summary card
    not_provided: str = ""  # recruiter text for "has not said ..."; the label when empty


@dataclass(frozen=True)
class Rule:
    """A reason that disqualifies a candidate. `applies` reads the screening's saved answers."""
    reason: str
    applies: Callable[[Any], bool]
    close: Text  # what the candidate is told
    summary: str  # what the recruiter reads


@dataclass(frozen=True)
class RecruiterTexts:
    """The recruiter's side: the summary card and the funnel, in the one language the recruiters read."""
    outcome_labels: dict[Outcome, str]
    no_name: str
    reason_prefix: str
    missing_prefix: str
    no_consent: str  # the reason when consent was declined
    blocked_on: str  # "has not said " + the field's not_provided text
    flags: dict[str, str]  # validation flag -> warning line
    footer: str
    chat_prefix: str
    language_word: str
    language_names: dict[Language, str]
    clarification: tuple[str, str]  # singular, plural
    asked_for_person: str
    reminder_sent: str
    started: str
    consented: str
    answered: str  # {label}
    qualified: str
    booked: str
    consent_stage: str


@dataclass(frozen=True)
class ScreeningSpec:
    fields: tuple[FieldSpec, ...]
    pack: Pack
    recruiter: RecruiterTexts
    rules: tuple[Rule, ...] = ()
    role: str = "job"  # "delivery-driver" in "a delivery-driver screening chat"
    area_field: str | None = None  # the field matched against the client's service areas
    title_field: str | None = None  # the answer that heads the summary card
    card_order: tuple[str, ...] = ()  # the fields that get a line on the card, in order

    @cached_property
    def extraction_model(self):
        return build_model(self)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields)

    def field(self, key: str) -> FieldSpec:
        for spec in self.fields:
            if spec.key == key:
                return spec
        raise ValueError(f"unknown field: {key}")

    def rule(self, reason: str) -> Rule:
        for rule in self.rules:
            if rule.reason == reason:
                return rule
        raise ValueError(f"unknown reason: {reason}")

    def close_text(self, reason: str) -> Text:
        return self.pack.close_no_consent if reason == Reason.NO_CONSENT else self.rule(reason).close
