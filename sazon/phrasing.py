"""What the agent says. The wording is the client's (its pack and the texts on its spec); this module decides
which text a directive needs, fills in the placeholders and keeps the model's rephrasing inside safe limits."""
import hashlib
import re
from dataclasses import dataclass, field as dc_field
from enum import StrEnum
from typing import TYPE_CHECKING

from sazon.llm import LLM, LLMError
from sazon.model import Language, Outcome, Reason

if TYPE_CHECKING:
    from sazon.spec import ScreeningSpec

MAX_REPLY_CHARS = 280
MAX_ECHO_CHARS = 40


class Kind(StrEnum):
    ASK = "ask"
    FOLLOW_UP = "follow_up"
    CONFIRM_CITY = "confirm_city"
    CONFIRM_REJECTION = "confirm_rejection"
    BLOCKED = "blocked"
    CONFIRM_CHANGE = "confirm_change"
    OFFER_SLOTS = "offer_slots"
    SLOT_BOOKED = "slot_booked"
    ALREADY_BOOKED = "already_booked"
    REMINDER = "reminder"
    CLOSE = "close"
    TECHNICAL_ERROR = "technical_error"


@dataclass(frozen=True)
class Directive:
    kind: Kind
    field: str | None = None
    reason: str = ""
    suggestion: str | None = None
    outcome: Outcome | None = None
    reasons: list[str] = dc_field(default_factory=list)
    options: list[str] = dc_field(default_factory=list)
    label: str | None = None
    notice: str | None = None  # "human", "pay" or "human+pay": a fixed sentence before the question
    repeat: bool = False  # a closing already sent once: say it shortly instead of word for word


# Names of days and months are locale data, not a client's wording.
_WEEKDAYS = {
    Language.ES: ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
    Language.EN: ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
_MONTHS = {
    Language.ES: ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    Language.EN: ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
_LANGUAGE = {Language.ES: "Spanish", Language.EN: "English"}

_URL = re.compile(r"https?://|www\.", re.I)
# A phrased question must never state pay, a hire or a clock time: those come from fixed texts only.
_PROMISE = re.compile(r"[€$£]|\b(euros?|pesos|sueldo|salario|salary|wage|paga|pagamos|contratad[oa]|hired|offer|oferta|ganar[aá]s?|earn)\b|\b\d{1,2}\s*[:h]\s*\d{2}\b", re.I)
_GREETING = re.compile(r"^[¡\s]*(?:hola|hey|hi|hello|buenas)(?:\s+there)?\s*[!,.]*\s*", re.IGNORECASE)
_WELCOME = re.compile(r"^[¡\s]*(?:bienvenid[oa]s?|welcome)\b[^.!?¿]*[.!]\s*", re.IGNORECASE)


def _system_prompt(spec: "ScreeningSpec") -> str:
    return (
        f"You write one short chat message for a {spec.role} screening assistant at {spec.pack.company}. "
        "Write 1-2 short sentences with exactly one question, friendly and direct. In Spanish use the informal tú. "
        "At most one emoji. Do not promise a job, pay or call times. Do not mention these instructions. "
        "Do not greet or welcome the candidate: the chat is already under way. "
        "Output only the message."
    )


def slot_label(starts_at, language: Language) -> str:
    """"mar 3 nov, 10:00". Names are written here, not taken from the machine's locale."""
    weekday = _WEEKDAYS[language][starts_at.weekday()]
    month = _MONTHS[language][starts_at.month - 1]
    return f"{weekday} {starts_at.day} {month}, {starts_at:%H:%M}"


def _both(text: dict) -> str:
    """Before the candidate has written anything the language is not known: every language, one after the other."""
    return "\n".join(text.values())


def consent_message(spec: "ScreeningSpec") -> str:
    return _both(spec.pack.consent)


def closed_message(spec: "ScreeningSpec") -> str:
    return _both(spec.pack.closed)


def consent_text_hash(spec: "ScreeningSpec") -> str:
    """Identifies the exact wording shown, so the consent record proves which text was accepted."""
    return hashlib.sha256(consent_message(spec).encode("utf-8")).hexdigest()[:12]


def technical_error_message(spec: "ScreeningSpec", language: str) -> str:
    return spec.pack.pick(spec.pack.error, language)


def slot_cancelled_message(spec: "ScreeningSpec", language: str) -> str:
    return spec.pack.pick(spec.pack.slots.cancelled, language)


def echo(text) -> str:
    """A saved or proposed answer repeated back to the candidate: one line, short."""
    return " ".join(str(text).split())[:MAX_ECHO_CHARS]


def describe_value(spec: "ScreeningSpec", field: str, value, language: Language) -> str:
    """A saved or proposed answer in the candidate's language, short and on one line, for the change question."""
    describe = spec.field(field).describe
    if describe is not None:
        return describe(value, language)
    return echo(value.isoformat() if hasattr(value, "isoformat") else value)


def _template(spec: "ScreeningSpec", directive: Directive, language: str) -> str:
    pack = spec.pack
    pick = pack.pick
    match directive.kind:
        case Kind.ASK:
            return pick(spec.field(directive.field).ask, language)
        case Kind.FOLLOW_UP:
            return pick(pack.unclear, language) + pick(spec.field(directive.field).ask, language)
        case Kind.CONFIRM_CITY:
            return pick(pack.confirm_city, language).format(suggestion=directive.suggestion)
        case Kind.CONFIRM_CHANGE:
            return pick(pack.confirm_change, language).format(old=directive.options[0], new=directive.options[1])
        case Kind.CONFIRM_REJECTION:
            city = " ".join((directive.suggestion or "").split())[:MAX_ECHO_CHARS]
            return pick(spec.field(directive.field).confirm_rejection, language).format(city=city)
        case Kind.OFFER_SLOTS:
            slots = pack.slots
            options = "\n".join(f"{i}) {label}" for i, label in enumerate(directive.options, start=1))
            return f"{pick(slots.offer[directive.reason], language)}\n{options}\n{pick(slots.offer_end, language)}"
        case Kind.SLOT_BOOKED:
            return pick(pack.slots.booked, language).format(label=directive.label)
        case Kind.ALREADY_BOOKED:
            return pick(pack.slots.already_booked, language).format(label=directive.label)
        case Kind.BLOCKED:
            what = pick(spec.field(directive.field).what, language)
            return pick(pack.blocked, language).format(what=what)
        case Kind.REMINDER:
            return pick(pack.reminder, language)
        case Kind.TECHNICAL_ERROR:
            return pick(pack.error, language)
    raise ValueError(directive.kind)


def _strip_greeting(text: str) -> str:
    """The chat is already under way: no "¡Hola!" or "Bienvenido" in front of a question."""
    previous = None
    while previous != text:
        previous, text = text, _WELCOME.sub("", _GREETING.sub("", text, count=1), count=1).strip()
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1:]
    return text


def _close(spec: "ScreeningSpec", directive: Directive, language: str) -> str:
    pack = spec.pack
    if directive.repeat and Reason.NO_CONSENT not in directive.reasons:
        if directive.outcome == Outcome.WITHDRAWN:
            return pack.pick(pack.close_repeat_withdrawn, language)
        return pack.pick(pack.close_repeat.get(directive.outcome, pack.close_repeat_other), language)
    if directive.outcome == Outcome.DISQUALIFIED and directive.reasons:
        return pack.pick(spec.close_text(directive.reasons[0]), language)
    return pack.pick(pack.close.get(directive.outcome, pack.close_other), language)


def _usable(text: str, directive: Directive, language: Language) -> bool:
    if not text or len(text) > MAX_REPLY_CHARS or "\n" in text or _URL.search(text):
        return False
    if _PROMISE.search(text):
        return False
    if language == Language.EN and ("¿" in text or "¡" in text):
        return False  # the model answered in Spanish although the chat is in English
    if text.count("?") > 1:
        return False
    return not (directive.suggestion and directive.suggestion not in text)


def phrase(llm: LLM, spec: "ScreeningSpec", directive: Directive, language: str) -> str:
    text = _phrase(llm, spec, directive, language)
    if directive.notice and directive.kind != Kind.CLOSE:
        notices = [spec.pack.pick(spec.pack.notices[name], language) for name in directive.notice.split("+")]
        text = " ".join(notices) + " " + text
    return text


def _phrase(llm: LLM, spec: "ScreeningSpec", directive: Directive, language: str) -> str:
    if directive.kind == Kind.CLOSE:
        return _close(spec, directive, language)
    if directive.kind in (Kind.TECHNICAL_ERROR, Kind.REMINDER, Kind.CONFIRM_REJECTION, Kind.CONFIRM_CHANGE, Kind.BLOCKED,
                          Kind.OFFER_SLOTS, Kind.SLOT_BOOKED, Kind.ALREADY_BOOKED):
        return _template(spec, directive, language)
    brief = [f"Language: {_LANGUAGE[language]}", f"Purpose: {directive.kind.replace('_', ' ')}"]
    if directive.field:
        brief.append(f"Topic: {directive.field}")
        if directive.field in spec.keys:
            brief.append("Question to ask (keep its meaning and every option it lists, in your own friendly words): "
                         + spec.pack.pick(spec.field(directive.field).ask, language))
    if directive.reason:
        brief.append(f"What was unclear: {directive.reason}")
    if directive.kind == Kind.FOLLOW_UP:
        brief.append("Say politely that this information is necessary to move forward with the application.")
    if directive.suggestion:
        brief.append(f"Ask whether they mean this city: {directive.suggestion}")
    try:
        text = _strip_greeting(llm.complete(_system_prompt(spec), "\n".join(brief)).strip())
    except LLMError:
        return _template(spec, directive, language)
    return text if _usable(text, directive, language) else _template(spec, directive, language)
