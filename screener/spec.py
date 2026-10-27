"""What a client defines to use the screening engine (D63): its fields, the rules that end a screening and its
wording. Everything here is data and small functions; the engine owns the flow."""
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from operator import eq
from typing import Any, Callable

from screener.extraction import ControlFlags, build_model
from screener.language import pick
from screener.model import NO_CONSENT, Language, Outcome
from screener.pack import Pack, Text
from screener.validators import Validation

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
    label: Text  # the recruiter's name for the field, in each recruiter language
    validate: Callable[[Any, date], Validation] | None = None  # None: the engine's area matching decides
    same: Callable[[Any, Any], bool] = eq  # compares validated values, so the same answer is never a change
    rejects: Callable[[Any], bool] | None = None  # an answer that ends the screening once the candidate confirms it
    confirm_rejection: Text | None = None  # asked before a rejecting answer counts; {area} is the candidate's text
    read: Callable[[Any, date, Any], object] | None = None  # (reply, today, base) -> a value or MISSING
    # base: what was kept of an earlier unclear answer, or the saved value when a change is being read
    partial: Callable[[Any], dict] | None = None  # what to keep of an unclear answer to combine with the next
    schema: dict[str, tuple] = field(default_factory=dict)  # the attributes this field adds to the model's reply
    prompt: str = ""  # the lines describing those attributes to the model
    decode_value: Callable[[Any], Any] | None = None  # a saved value read back from JSON
    decode_candidate: Callable[[Any], Any] | None = None  # a pending change read back from JSON
    describe: Callable[[Any, Language], str] | None = None  # a value in the candidate's words, for a change question
    card: Callable[[Any, Language], str] | None = None  # the line for the recruiter's summary card
    not_provided: Text | None = None  # recruiter text for "has not said ..."; the label when None


@dataclass(frozen=True)
class Rule:
    """A reason that disqualifies a candidate. `applies` reads the screening's saved answers."""
    reason: str
    applies: Callable[[Any], bool]
    close: Text  # what the candidate is told
    summary: Text  # what the recruiter reads, in each recruiter language


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
    recruiter: dict[Language, RecruiterTexts]  # one per language the recruiters read; includes the default one
    rules: tuple[Rule, ...] = ()
    role: str = "job"  # "warehouse-picker" in "a warehouse-picker screening chat"
    area_field: str | None = None  # the field matched against the client's service areas
    place_qualifiers: tuple[str, ...] = ()  # words that may follow a place ("Leeds, England") and are dropped
    persona: str = ""  # how the assistant sounds, written for the model (tone, length, form of address)
    title_field: str | None = None  # the answer that heads the summary card
    card_order: tuple[str, ...] = ()  # the fields that get a line on the card, in order

    def __post_init__(self):
        check_spec(self)

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

    def recruiter_texts(self, language: Language | None = None) -> RecruiterTexts:
        """The recruiter words in `language`, or in the pack's default language when that one is not listed."""
        return pick(self.recruiter, language, self.pack.default_language)

    def say(self, text: Text, language: Language | None = None) -> str:
        """A recruiter-facing text in `language`, or in the default language."""
        return pick(text, language, self.pack.default_language)

    def reason_text(self, code: str, language: Language | None = None) -> str:
        """A disqualifying or blocking reason in the recruiter's words."""
        texts = self.recruiter_texts(language)
        if code == NO_CONSENT:
            return texts.no_consent
        if code.startswith("BLOCKED_ON_"):
            field = self.field(code.removeprefix("BLOCKED_ON_").lower())
            return texts.blocked_on + self.say(field.not_provided or field.label, language)
        try:
            return self.say(self.rule(code).summary, language)
        except ValueError:
            return code

    def close_text(self, reason: str) -> Text:
        return self.pack.close_no_consent if reason == NO_CONSENT else self.rule(reason).close


class SpecError(ValueError):
    """A spec that cannot run. The message lists every problem found."""


_NOTICES = ("human", "pay", "changed", "kept", "offtopic")
_CLOSES = (Outcome.QUALIFIED, Outcome.ENDED_OFF_TOPIC, Outcome.WITHDRAWN)
_OFFERS = ("first", "taken", "unclear", "reminder")


def check_spec(spec: "ScreeningSpec") -> None:
    """Raises SpecError naming everything the engine would otherwise only discover in the middle of a chat."""
    problems: list[str] = []
    default = spec.pack.default_language

    def need_text(where: str, text) -> None:
        if not text or not text.get(default):
            problems.append(f"{where} has no text in {default}")

    def need_recruiter_text(where: str, text) -> None:
        missing = [str(language) for language in spec.recruiter if not text or not text.get(language)]
        if missing:
            problems.append(f"{where} has no text in the recruiter language {', '.join(missing)}")

    if default not in spec.recruiter:
        problems.append(f"recruiter has no texts in the default language {default}")
    keys = spec.keys
    for key in dict.fromkeys(keys):
        if keys.count(key) > 1:
            problems.append(f"field '{key}' is listed twice")
    attributes: dict[str, str] = {}
    for f in spec.fields:
        if f.read is None:
            problems.append(f"field '{f.key}' has no read function")
        if f.validate is None and f.key != spec.area_field:
            problems.append(f"field '{f.key}' has no validate function")
        need_text(f"field '{f.key}': ask", f.ask)
        need_text(f"field '{f.key}': what", f.what)
        need_recruiter_text(f"field '{f.key}': label", f.label)
        if f.not_provided is not None:
            need_recruiter_text(f"field '{f.key}': not_provided", f.not_provided)
        if f.rejects is not None:
            need_text(f"field '{f.key}': confirm_rejection", f.confirm_rejection)
        for name in f.schema:
            if name in ControlFlags.model_fields or name in attributes:
                problems.append(f"reply attribute '{name}' of field '{f.key}' is already taken")
            attributes[name] = f.key
    if spec.area_field is not None and spec.area_field not in keys:
        problems.append(f"area_field '{spec.area_field}' is not a field")
    if spec.title_field is not None and spec.title_field not in keys:
        problems.append(f"title_field '{spec.title_field}' is not a field")
    for key in spec.card_order:
        if key not in keys:
            problems.append(f"card_order names '{key}', which is not a field")
        elif spec.field(key).card is None:
            problems.append(f"field '{key}' is in card_order but has no card function")
    reasons = [rule.reason for rule in spec.rules]
    for reason in dict.fromkeys(reasons):
        if reasons.count(reason) > 1:
            problems.append(f"reason {reason} is used by two rules")
    for rule in spec.rules:
        if rule.reason == NO_CONSENT:
            problems.append("NO_CONSENT is the engine's own reason")
        need_text(f"rule {rule.reason}: close", rule.close)
        need_recruiter_text(f"rule {rule.reason}: summary", rule.summary)
    pack = spec.pack
    for name in ("consent", "closed", "error", "reminder", "unclear", "confirm_area", "confirm_change", "blocked",
                 "close_other", "close_no_consent", "close_repeat_withdrawn", "close_repeat_other"):
        need_text(f"pack.{name}", getattr(pack, name))
    for outcome in _CLOSES:
        need_text(f"pack.close[{outcome}]", pack.close.get(outcome))
    for name in _NOTICES:
        need_text(f"pack.notices[{name}]", pack.notices.get(name))
    if pack.slots is not None:
        for name in _OFFERS:
            need_text(f"pack.slots.offer[{name}]", pack.slots.offer.get(name))
        for name in ("offer_end", "booked", "already_booked", "cancelled"):
            need_text(f"pack.slots.{name}", getattr(pack.slots, name))
    for language, texts in spec.recruiter.items():
        for outcome in Outcome:
            if outcome not in texts.outcome_labels:
                problems.append(f"recruiter[{language}].outcome_labels has no label for {outcome}")
        for candidate_language in pack.consent:
            if candidate_language not in texts.language_names:
                problems.append(f"recruiter[{language}].language_names has no name for {candidate_language}")
    if problems:
        raise SpecError("; ".join(problems))
