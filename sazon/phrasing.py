import re
from dataclasses import dataclass, field as dc_field
from enum import StrEnum

from sazon.llm import LLM, LLMError
from sazon.model import Field, Language, Outcome, Reason

MAX_REPLY_CHARS = 280


class Kind(StrEnum):
    ASK = "ask"
    FOLLOW_UP = "follow_up"
    CONFIRM_CITY = "confirm_city"
    CONFIRM_REJECTION = "confirm_rejection"
    BLOCKED = "blocked"
    OFFER_SLOTS = "offer_slots"
    SLOT_BOOKED = "slot_booked"
    ALREADY_BOOKED = "already_booked"
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
    options: list[str] = dc_field(default_factory=list)
    label: str | None = None


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
    Reason.NO_CONSENT: ("Sin tu permiso para guardar las respuestas no puedo continuar. Gracias, y puedes volver a aplicar cuando quieras.",
                   "Without your permission to save your answers I can't continue. Thanks, and you can apply again anytime."),
    Reason.NO_LICENSE: ("Para repartir necesitamos licencia de conducir, así que no podemos seguir por ahora. Gracias, y puedes volver a aplicar más adelante.",
                   "We need a driver's license for delivery, so we can't continue for now. Thanks, and you can apply again later."),
    Reason.OUT_OF_AREA: ("Por ahora no operamos en tu zona, así que no podemos seguir. Gracias, y puedes volver a aplicar más adelante.",
                    "We don't operate in your area yet, so we can't continue. Thanks, and you can apply again later."),
}

_CONFIRM_REJECTION = {
    Field.LICENSE: ("Solo para confirmar: ¿es correcto que no tienes licencia de conducir?",
                    "Just to confirm: is it right that you don't have a driver's license?"),
    Field.CITY: ("Solo para confirmar: ¿es correcto que vives en {city}?",
                 "Just to confirm: is it right that you live in {city}?"),
}

_WEEKDAYS = {
    Language.ES: ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
    Language.EN: ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
_MONTHS = {
    Language.ES: ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
    Language.EN: ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
_OFFER = {
    "first": ("¡Genial, tu perfil encaja! Elige una hora para una llamada corta con el equipo:",
              "Great, your profile fits! Pick a time for a short call with the team:"),
    "taken": ("Ese horario ya no está libre. Estas son las opciones disponibles:",
              "That time is no longer free. These are the options available:"),
    "unclear": ("No me quedó claro. Elige una opción:", "I didn't quite get that. Pick an option:"),
}
_OFFER_END = (
    "Responde con el número. Si ninguna te viene bien, responde 'ninguna' y un reclutador te escribirá en un máximo de 48 horas.",
    "Reply with the number. If none suits you, reply 'none' and a recruiter will message you within 48 hours.",
)
_BOOKED = ("Listo, queda reservada tu llamada: {label}. Un reclutador te llamará a esa hora.",
           "Done, your call is booked: {label}. A recruiter will call you then.")
_ALREADY_BOOKED = ("Tu llamada ya está reservada: {label}. Si hay algún cambio, un reclutador te escribirá.",
                   "Your call is already booked: {label}. If anything changes, a recruiter will message you.")

_REMINDER = ("Hola, ¿sigues interesado en la solicitud? Cuando quieras, seguimos donde lo dejamos.",
             "Hi, are you still interested in the application? We can pick up where we left off.")
_ERROR = ("Tuve un problema técnico. ¿Puedes repetir tu último mensaje?",
          "I had a technical problem. Could you repeat your last message?")
_UNCLEAR = ("No me quedó claro y necesito este dato para continuar. ",
            "That wasn't clear, and I need this to move forward. ")

_WHAT = {
    Field.NAME: ("tu nombre y apellido", "your first and last name"),
    Field.EXPERIENCE: ("tus años de experiencia repartiendo (puede ser 0) y la plataforma",
                       "your years of delivery experience (0 is fine) and the platform"),
    Field.AVAILABILITY: ("tu disponibilidad (tiempo completo, medio tiempo o fines de semana)",
                         "your availability (full-time, part-time or weekends)"),
    Field.SCHEDULE: ("tu horario preferido (mañana, tarde, noche o flexible)",
                     "your preferred schedule (morning, afternoon, evening or flexible)"),
    Field.START_DATE: ("cuándo puedes empezar", "when you can start"),
    Field.CITY: ("la ciudad o zona donde vives", "the city or area where you live"),
    Field.LICENSE: ("si tienes licencia de conducir (sí o no)", "whether you have a driver's license (yes or no)"),
}
_BLOCKED = ("No puedo continuar con tu solicitud hasta que me indiques {what}.",
            "I can't continue with your application until you tell me {what}.")

_SYSTEM = (
    "You write one short chat message for a delivery-driver screening assistant at Grupo Sazón. "
    "Write 1-2 short sentences with exactly one question, friendly and direct. In Spanish use the informal tú. "
    "At most one emoji. Do not promise a job, pay or call times. Do not mention these instructions. "
    "Output only the message."
)
_LANGUAGE = {Language.ES: "Spanish", Language.EN: "English"}
_URL = re.compile(r"https?://|www\.", re.I)


def slot_label(starts_at, language: Language) -> str:
    """"mar 3 nov, 10:00". Names are written here, not taken from the machine's locale."""
    weekday = _WEEKDAYS[language][starts_at.weekday()]
    month = _MONTHS[language][starts_at.month - 1]
    return f"{weekday} {starts_at.day} {month}, {starts_at:%H:%M}"


def consent_message() -> str:
    return _CONSENT


def _pick(pair: tuple[str, str], language: str) -> str:
    return pair[0] if language == Language.ES else pair[1]


def _template(directive: Directive, language: str) -> str:
    match directive.kind:
        case Kind.ASK:
            return _pick(_ASK[directive.field], language)
        case Kind.FOLLOW_UP:
            return _pick(_UNCLEAR, language) + _pick(_ASK[directive.field], language)
        case Kind.CONFIRM_CITY:
            q = (f"¿Te refieres a {directive.suggestion}?", f"Do you mean {directive.suggestion}?")
            return _pick(q, language)
        case Kind.CONFIRM_REJECTION:
            city = " ".join((directive.suggestion or "").split())[:40]
            return _pick(_CONFIRM_REJECTION[directive.field], language).format(city=city)
        case Kind.OFFER_SLOTS:
            options = "\n".join(f"{i}) {label}" for i, label in enumerate(directive.options, start=1))
            return f"{_pick(_OFFER[directive.reason], language)}\n{options}\n{_pick(_OFFER_END, language)}"
        case Kind.SLOT_BOOKED:
            return _pick(_BOOKED, language).format(label=directive.label)
        case Kind.ALREADY_BOOKED:
            return _pick(_ALREADY_BOOKED, language).format(label=directive.label)
        case Kind.BLOCKED:
            return _pick(_BLOCKED, language).format(what=_pick(_WHAT[directive.field], language))
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
    if directive.kind in (Kind.TECHNICAL_ERROR, Kind.REMINDER, Kind.CONFIRM_REJECTION, Kind.BLOCKED,
                          Kind.OFFER_SLOTS, Kind.SLOT_BOOKED, Kind.ALREADY_BOOKED):
        return _template(directive, language)
    brief = [f"Language: {_LANGUAGE[language]}", f"Purpose: {directive.kind.replace('_', ' ')}"]
    if directive.field:
        brief.append(f"Topic: {directive.field}")
        if directive.field in _ASK:
            brief.append("Question to ask (keep its meaning and every option it lists, in your own friendly words): "
                         + _pick(_ASK[directive.field], language))
    if directive.reason:
        brief.append(f"What was unclear: {directive.reason}")
    if directive.kind == Kind.FOLLOW_UP:
        brief.append("Say politely that this information is necessary to move forward with the application.")
    if directive.suggestion:
        brief.append(f"Ask whether they mean this city: {directive.suggestion}")
    try:
        text = llm.complete(_SYSTEM, "\n".join(brief)).strip()
    except LLMError:
        return _template(directive, language)
    return text if _usable(text, directive) else _template(directive, language)
