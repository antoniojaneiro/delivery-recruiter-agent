import re
from dataclasses import dataclass, field as dc_field
from enum import StrEnum

from sazon.llm import LLM, LLMError
from sazon.model import Field, Outcome

MAX_REPLY_CHARS = 280


class Kind(StrEnum):
    ASK = "ask"
    FOLLOW_UP = "follow_up"
    CONFIRM_CITY = "confirm_city"
    REMINDER = "reminder"
    CLOSE = "close"
    TECHNICAL_ERROR = "technical_error"


@dataclass(frozen=True)
class Directive:
    kind: Kind
    field: Field | None = None
    reason: str = ""
    suggestion: str | None = None
    outcome: Outcome | None = None
    reasons: list[str] = dc_field(default_factory=list)


_CONSENT = (
    "Hola, soy el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud "
    "de repartidor. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?\n"
    "Hi, I'm Grupo Sazón's virtual assistant (an AI). I'll ask a few questions for your delivery "
    "driver application. Is it OK if I save your answers for the recruiting team?"
)

_ASK = {
    Field.NAME: ("¿Cómo te llamas? Necesito tu nombre y apellido.", "What's your full name, first and last?"),
    Field.EXPERIENCE: ("¿Tienes experiencia repartiendo? Dime cuántos años y en qué plataforma.",
                       "Do you have delivery experience? Tell me how many years and on which platform."),
    Field.AVAILABILITY: ("¿Qué disponibilidad tienes: tiempo completo, medio tiempo o fines de semana?",
                         "What's your availability: full-time, part-time or weekends?"),
    Field.SCHEDULE: ("¿Qué horario prefieres: mañana, tarde, noche o flexible?",
                     "Which schedule do you prefer: morning, afternoon, evening or flexible?"),
    Field.START_DATE: ("¿Cuándo podrías empezar?", "When could you start?"),
    Field.CITY: ("¿En qué ciudad o zona vives?", "Which city or area do you live in?"),
    Field.LICENSE: ("¿Tienes licencia de conducir?", "Do you have a driver's license?"),
}

_CLOSE = {
    Outcome.QUALIFIED: (
        "¡Genial, tu perfil encaja! Un reclutador te escribirá en un máximo de 48 horas para el siguiente paso.",
        "Great, your profile fits! A recruiter will message you within 48 hours with the next step."),
    Outcome.ENDED_OFF_TOPIC: (
        "Parece que no podemos seguir con la solicitud ahora. Si quieres retomarla, escríbenos de nuevo.",
        "It looks like we can't continue the application right now. Write to us again to pick it up."),
    Outcome.WITHDRAWN: (
        "Entendido, paramos aquí y no te haré más preguntas. Gracias por tu tiempo.",
        "Understood, we'll stop here and I won't ask anything more. Thanks for your time."),
}
_CLOSE_REASON = {
    "NO_CONSENT": ("Sin tu permiso para guardar las respuestas no puedo continuar. Gracias, y puedes volver a aplicar cuando quieras.",
                   "Without your permission to save your answers I can't continue. Thanks, and you can apply again anytime."),
    "NO_LICENSE": ("Para repartir necesitamos licencia de conducir, así que no podemos seguir por ahora. Gracias, y puedes volver a aplicar más adelante.",
                   "We need a driver's license for delivery, so we can't continue for now. Thanks, and you can apply again later."),
    "OUT_OF_AREA": ("Por ahora no operamos en tu zona, así que no podemos seguir. Gracias, y puedes volver a aplicar más adelante.",
                    "We don't operate in your area yet, so we can't continue. Thanks, and you can apply again later."),
}

_REMINDER = ("Hola, ¿sigues interesado en la solicitud? Cuando quieras, seguimos donde lo dejamos.",
             "Hi, are you still interested in the application? We can pick up where we left off.")
_ERROR = ("Tuve un problema técnico. ¿Puedes repetir tu último mensaje?",
          "I had a technical problem. Could you repeat your last message?")
_UNCLEAR = ("No me quedó claro. ", "I didn't quite get that. ")

_SYSTEM = (
    "You write one short chat message for a delivery-driver screening assistant at Grupo Sazón. "
    "Write 1-2 short sentences with exactly one question, friendly and direct. In Spanish use the informal tú. "
    "At most one emoji. Do not promise a job, pay or call times. Do not mention these instructions. "
    "Output only the message."
)
_LANGUAGE = {"es": "Spanish", "en": "English"}
_URL = re.compile(r"https?://|www\.", re.I)


def consent_message() -> str:
    return _CONSENT


def _pick(pair: tuple[str, str], language: str) -> str:
    return pair[0] if language == "es" else pair[1]


def _template(directive: Directive, language: str) -> str:
    match directive.kind:
        case Kind.ASK:
            return _pick(_ASK[directive.field], language)
        case Kind.FOLLOW_UP:
            return _pick(_UNCLEAR, language) + _pick(_ASK[directive.field], language)
        case Kind.CONFIRM_CITY:
            q = (f"¿Te refieres a {directive.suggestion}?", f"Do you mean {directive.suggestion}?")
            return _pick(q, language)
        case Kind.REMINDER:
            return _pick(_REMINDER, language)
        case Kind.TECHNICAL_ERROR:
            return _pick(_ERROR, language)
    raise ValueError(directive.kind)


def _close(directive: Directive, language: str) -> str:
    if directive.outcome == Outcome.DISQUALIFIED:
        return _pick(_CLOSE_REASON[directive.reasons[0]], language)
    return _pick(_CLOSE[directive.outcome], language)


def _usable(text: str, directive: Directive) -> bool:
    if not text or len(text) > MAX_REPLY_CHARS or "\n" in text or _URL.search(text):
        return False
    if text.count("?") > 1:
        return False
    return not (directive.suggestion and directive.suggestion not in text)


def phrase(llm: LLM, directive: Directive, language: str) -> str:
    if directive.kind == Kind.CLOSE:
        return _close(directive, language)
    if directive.kind in (Kind.TECHNICAL_ERROR, Kind.REMINDER):
        return _template(directive, language)
    brief = [f"Language: {_LANGUAGE[language]}", f"Purpose: {directive.kind.replace('_', ' ')}"]
    if directive.field:
        brief.append(f"Topic: {directive.field}")
    if directive.reason:
        brief.append(f"What was unclear: {directive.reason}")
    if directive.suggestion:
        brief.append(f"Ask whether they mean this city: {directive.suggestion}")
    try:
        text = llm.complete(_SYSTEM, "\n".join(brief)).strip()
    except LLMError:
        return _template(directive, language)
    return text if _usable(text, directive) else _template(directive, language)
