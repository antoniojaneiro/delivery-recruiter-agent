"""Grupo Sazón's screening: delivery drivers in Spain and Mexico (D63)."""
from datetime import date
from typing import Literal

from screener import validators

from sazon import validators as checks
from screener.extraction import StartDate, build_system_prompt
from screener.model import Language, Outcome
from sazon.fields import Field, Reason
from screener.phrasing import echo
from screener.language import fold
from sazon.pack import PACK, bi
from screener.spec import MISSING, FieldSpec, RecruiterTexts, Rule, ScreeningSpec, read_attribute

ES, EN = Language.ES, Language.EN


def _experience(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return validators.Validation(False, reason="need years and platform")
    return checks.validate_experience(*value)


def _read_experience(reply, today, base):
    """Zero years is something the candidate says (`no_experience`); a zero the model wrote for a plain yes is ignored."""
    if reply.no_experience:
        return (0, [])
    stated = reply.experience_years if reply.experience_years else None  # 0.0 without the flag is not an answer
    if stated is None and not reply.platforms:
        return MISSING
    base = base or {}
    years = stated if stated is not None else base.get("years")
    return (years, reply.platforms or base.get("platforms", []))


def _read_start_date(reply, today, base):
    return reply.start_date.resolve(today) if reply.start_date is not None else MISSING


def _date_from_json(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


_AVAILABILITY = {"full_time": bi("tiempo completo", "full-time"), "part_time": bi("medio tiempo", "part-time"),
                 "weekends": bi("fines de semana", "weekends")}
_SCHEDULE = {"morning": bi("mañana", "morning"), "afternoon": bi("tarde", "afternoon"),
             "evening": bi("noche", "evening"), "flexible": bi("flexible", "flexible")}


def _word(words: dict, value, language: Language) -> str:
    return words[value][language] if value in words else echo(value)


def _describe_license(value, language: Language) -> str:
    return {ES: "sí", EN: "yes"}[language] if value else "no"


def _describe_availability(value, language: Language) -> str:
    return ", ".join(_word(_AVAILABILITY, v, language) for v in value)


def _describe_schedule(value, language: Language) -> str:
    return _word(_SCHEDULE, value, language)


def _describe_experience(value, language: Language) -> str:
    years, platforms = (value["years"], value["platforms"]) if isinstance(value, dict) else value
    if not years:
        return {ES: "sin experiencia", EN: "no experience"}[language]
    unit = {ES: "año" if years == 1 else "años", EN: "year" if years == 1 else "years"}[language]
    shown = f"{years:g} {unit}"
    return f"{shown} ({', '.join(echo(p) for p in platforms)})" if platforms else shown


_CARD_LABEL = {
    "license": {ES: "Licencia: ", EN: "License: "},
    "experience": {ES: "Experiencia: ", EN: "Experience: "},
    "availability": {ES: "Disponibilidad: ", EN: "Availability: "},
    "schedule": {ES: "Horario preferido: ", EN: "Preferred schedule: "},
    "start": {ES: "Inicio: ", EN: "Start: "},
}
_CARD_AVAILABILITY = {
    ES: {"full_time": "tiempo completo", "part_time": "medio tiempo", "weekends": "fines de semana"},
    EN: {"full_time": "full-time", "part_time": "part-time", "weekends": "weekends"},
}
_CARD_SCHEDULE = {
    ES: {"morning": "mañana", "afternoon": "tarde", "evening": "noche", "flexible": "flexible"},
    EN: {"morning": "morning", "afternoon": "afternoon", "evening": "evening", "flexible": "flexible"},
}


def _card_experience(value, language: Language) -> str:
    years, platforms = value["years"], value["platforms"]
    label = _CARD_LABEL["experience"][language]
    if not years:
        return label + {ES: "sin experiencia", EN: "no experience"}[language]
    unit = {ES: "año" if years == 1 else "años", EN: "year" if years == 1 else "years"}[language]
    shown = f"{years:g} {unit}"
    return label + (f"{shown} ({', '.join(platforms)})" if platforms else shown)

_RECRUITER_ES = RecruiterTexts(
    outcome_labels={
        Outcome.IN_PROGRESS: "En curso",
        Outcome.QUALIFIED: "Cualificado",
        Outcome.DISQUALIFIED: "Descartado por el agente",
        Outcome.BLOCKED: "Bloqueado",
        Outcome.STALLED: "Sin respuesta",
        Outcome.ENDED_OFF_TOPIC: "Terminó fuera de tema",
        Outcome.WITHDRAWN: "Se retiró",
    },
    no_name="Candidato sin nombre", reason_prefix="Motivo: ", missing_prefix="Falta: ",
    no_consent="no dio su consentimiento", blocked_on="no ha indicado ",
    flags={"START_DATE_FAR": "Aviso: la fecha de inicio está a más de 12 semanas"},
    footer="Resumen automático: la decisión final es del reclutador.",
    chat_prefix="Chat: ", language_word="idioma", language_names={ES: "español", EN: "inglés"},
    clarification=("aclaración", "aclaraciones"), asked_for_person="pidió hablar con una persona",
    reminder_sent="recordatorio enviado",
    started="Empezaron", consented="Dieron su consentimiento", answered="Respondieron: {label}",
    qualified="Cualificaron", booked="Reservaron una llamada", consent_stage="consentimiento",
)

_RECRUITER_EN = RecruiterTexts(
    outcome_labels={
        Outcome.IN_PROGRESS: "In progress",
        Outcome.QUALIFIED: "Qualified",
        Outcome.DISQUALIFIED: "Rejected by the agent",
        Outcome.BLOCKED: "Blocked",
        Outcome.STALLED: "No reply",
        Outcome.ENDED_OFF_TOPIC: "Ended off topic",
        Outcome.WITHDRAWN: "Withdrew",
    },
    no_name="Candidate without a name", reason_prefix="Reason: ", missing_prefix="Missing: ",
    no_consent="did not give consent", blocked_on="has not said ",
    flags={"START_DATE_FAR": "Warning: the start date is more than 12 weeks away"},
    footer="Automatic summary: the recruiter makes the final decision.",
    chat_prefix="Chat: ", language_word="language", language_names={ES: "Spanish", EN: "English"},
    clarification=("clarification", "clarifications"), asked_for_person="asked to speak to a person",
    reminder_sent="reminder sent",
    started="Started", consented="Gave consent", answered="Answered: {label}",
    qualified="Qualified", booked="Booked a call", consent_stage="consent",
)

RECRUITER = {ES: _RECRUITER_ES, EN: _RECRUITER_EN}

SAZON = ScreeningSpec(
    role="delivery-driver",
    persona=("Warm, direct and respectful, like a friendly recruiter chatting on a phone. Short messages, one question at "
             "a time, at most one emoji, no jargon. In Spanish use the informal tú. Acknowledge what the candidate "
             "just said in a few words before asking the next thing, and vary your wording; never repeat a sentence "
             "you already wrote."),
    pack=PACK,
    recruiter=RECRUITER,
    title_field=Field.NAME,
    card_order=(Field.LICENSE, Field.EXPERIENCE, Field.AVAILABILITY, Field.SCHEDULE, Field.START_DATE),
    fields=(
        FieldSpec(Field.NAME, ask=bi("¿Cómo te llamas? Necesito tu nombre y apellido.",
                                     "What's your full name, first and last?"),
                  what=bi("tu nombre y apellido", "your first and last name"),
                  label=bi("nombre", "name"), not_provided=bi("su nombre", "their name"),
                  validate=lambda value, today: validators.validate_name(value),
                  same=lambda old, new: fold(old) == fold(new),
                  read=read_attribute("name"), schema={"name": (str | None, None)},
                  prompt="- name: full name as written"),
        FieldSpec(Field.EXPERIENCE,
                  ask=bi("¿Tienes experiencia repartiendo? Dime cuántos años y en qué plataforma.",
                         "Do you have delivery experience? Tell me how many years and on which platform."),
                  what=bi("tus años de experiencia repartiendo (puede ser 0) y la plataforma",
                          "your years of delivery experience (0 is fine) and the platform"),
                  label=bi("experiencia", "experience"), not_provided=bi("su experiencia", "their experience"),
                  validate=lambda value, today: _experience(value),
                  same=lambda old, new: old["years"] == new["years"] and set(old["platforms"]) == set(new["platforms"]),
                  read=_read_experience, partial=lambda value: {"years": value[0], "platforms": value[1]},
                  decode_candidate=tuple, describe=_describe_experience, card=_card_experience,
                  schema={"experience_years": (float | None, None), "no_experience": (bool | None, None),
                          "platforms": (list[str], [])},
                  prompt="- experience_years: the number of years of delivery experience they state; null when they give "
                         "no number (a plain yes is not a number)\n"
                         "- no_experience: true only if they say they have no delivery experience; never for a plain yes\n"
                         "- platforms: delivery platforms mentioned, as written (e.g. Glovo, Uber Eats)"),
        FieldSpec(Field.AVAILABILITY,
                  ask=bi("¿Qué disponibilidad tienes: tiempo completo, medio tiempo o fines de semana?",
                         "What's your availability: full-time, part-time or weekends?"),
                  what=bi("tu disponibilidad (tiempo completo, medio tiempo o fines de semana)",
                          "your availability (full-time, part-time or weekends)"),
                  label=bi("disponibilidad", "availability"), not_provided=bi("su disponibilidad", "their availability"),
                  validate=lambda value, today: checks.validate_availability(value),
                  same=lambda old, new: set(old) == set(new),
                  read=read_attribute("availability", empty_is_missing=True), describe=_describe_availability,
                  card=lambda value, language: _CARD_LABEL["availability"][language] + ", ".join(
                      _CARD_AVAILABILITY[language][a] for a in value),
                  schema={"availability": (list[Literal["full_time", "part_time", "weekends"]], [])},
                  prompt='- availability: any of "full_time", "part_time", "weekends". Use "weekends" only if they name weekends, '
                         'Saturday or Sunday. A number of days or hours a week that is less than a full job (for example '
                         '"2 days a week") is "part_time". Leave it null if it is unclear'),
        FieldSpec(Field.SCHEDULE,
                  ask=bi("¿Qué horario prefieres: mañana, tarde, noche o flexible?",
                         "Which schedule do you prefer: morning, afternoon, evening or flexible?"),
                  what=bi("tu horario preferido (mañana, tarde, noche o flexible)",
                          "your preferred schedule (morning, afternoon, evening or flexible)"),
                  label=bi("horario preferido", "preferred schedule"), not_provided=bi("su horario preferido", "their preferred schedule"),
                  validate=lambda value, today: checks.validate_schedule(value),
                  read=read_attribute("schedule"), describe=_describe_schedule,
                  card=lambda value, language: _CARD_LABEL["schedule"][language] + _CARD_SCHEDULE[language][value],
                  schema={"schedule": (Literal["morning", "afternoon", "evening", "flexible"] | None, None)},
                  prompt='- schedule: one of "morning", "afternoon", "evening", "flexible"'),
        FieldSpec(Field.START_DATE, ask=bi("¿Cuándo podrías empezar?", "When could you start?"),
                  what=bi("cuándo puedes empezar", "when you can start"),
                  label=bi("fecha de inicio", "start date"), not_provided=bi("su fecha de inicio", "their start date"),
                  validate=checks.validate_start_date, read=_read_start_date,
                  decode_value=_date_from_json, decode_candidate=_date_from_json,
                  card=lambda value, language: _CARD_LABEL["start"][language] + value,
                  schema={"start_date": (StartDate | None, None)},
                  prompt='- start_date: {"iso": "YYYY-MM-DD"} for an exact date, else {"now": true}, {"in_days": n} or '
                         '{"in_weeks": n}, {"in_months": n}, or {"weekday": 0-6} (Monday=0) for "next Monday" or '
                         '"el lunes". Never do date arithmetic yourself.'),
        FieldSpec(Field.CITY, ask=bi("¿En qué ciudad o zona vives?", "Which city or area do you live in?"),
                  what=bi("la ciudad o zona donde vives", "the city or area where you live"),
                  label=bi("ciudad", "city"), not_provided=bi("su ciudad", "their city"),
                  confirm_rejection=bi("Solo para confirmar: ¿es correcto que vives en {area}?",
                                       "Just to confirm: is it right that you live in {area}?"),
                  read=read_attribute("city"), schema={"city": (str | None, None)},
                  prompt="- city: the city or zone exactly as written, never mapped or corrected"),
        FieldSpec(Field.LICENSE, ask=bi("¿Tienes licencia de conducir?", "Do you have a driver's license?"),
                  what=bi("si tienes licencia de conducir (sí o no)", "whether you have a driver's license (yes or no)"),
                  label=bi("licencia", "license"), not_provided=bi("si tiene licencia de conducir", "whether they hold a driver's license"),
                  validate=lambda value, today: checks.validate_license(value),
                  rejects=lambda value: value is False, read=read_attribute("has_license"),
                  confirm_rejection=bi("Solo para confirmar: ¿es correcto que no tienes licencia de conducir?",
                                       "Just to confirm: is it right that you don't have a driver's license?"),
                  describe=_describe_license, card=lambda value, language: _CARD_LABEL["license"][language] + (
                      {ES: "sí", EN: "yes"}[language] if value else "no"),
                  schema={"has_license": (bool | None, None)},
                  prompt="- has_license: true/false only if they clearly state whether they hold a driver's license. "
                         "A license is not a car,\n  motorbike, bike or any vehicle: not owning a vehicle says nothing "
                         "about the license (leave it null)"),
    ),
    rules=(
        Rule(Reason.NO_LICENSE, applies=lambda screening: screening.values.get(Field.LICENSE) is False,
             close=bi("Para repartir necesitamos licencia de conducir, así que no puedo seguir con el proceso automático. "
                      "Un reclutador puede revisar tu caso si hay algún error. Gracias por tu interés.",
                      "We need a driver's license for delivery, so I can't continue with the automated process. "
                      "A recruiter can review your case if something is wrong. Thanks for your interest."),
             summary=bi("no tiene licencia de conducir", "no driver's license")),
        Rule(Reason.OUT_OF_AREA, applies=lambda screening: screening.out_of_area,
             close=bi("Por ahora no operamos en tu zona, así que no puedo seguir con el proceso automático. "
                      "Un reclutador puede revisar tu caso si hay algún error. Gracias por tu interés.",
                      "We don't operate in your area yet, so I can't continue with the automated process. "
                      "A recruiter can review your case if something is wrong. Thanks for your interest."),
             summary=bi("fuera de la zona de servicio", "outside the service area")),
    ),
    area_field=Field.CITY,
    # A country or state written after the place ("Madrid, España") is dropped; any other suffix is kept.
    place_qualifiers=("espana", "spain", "mexico", "jalisco", "nuevo leon", "comunidad de madrid", "cataluna",
                      "catalunya", "comunitat valenciana", "estado de mexico", "edomex"),
)

Extraction = SAZON.extraction_model
SYSTEM = build_system_prompt(SAZON)
