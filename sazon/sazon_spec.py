"""Grupo Sazón's screening: delivery drivers in Spain and Mexico (D63)."""
from datetime import date
from typing import Literal

from sazon import sazon_validators as checks, validators
from sazon.extraction import StartDate, build_system_prompt
from sazon.model import Language, Outcome
from sazon.sazon_fields import Field, Reason
from sazon.phrasing import echo
from sazon.sazon_pack import PACK, bi
from sazon.spec import MISSING, FieldSpec, RecruiterTexts, Rule, ScreeningSpec, read_attribute

ES, EN = Language.ES, Language.EN


def _experience(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return validators.Validation(False, reason="need years and platform")
    return checks.validate_experience(*value)


def _read_experience(reply, today, base):
    if reply.experience_years is None and not reply.platforms:
        return MISSING
    base = base or {}
    years = reply.experience_years if reply.experience_years is not None else base.get("years")
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


def _card_experience(value) -> str:
    years, platforms = value["years"], value["platforms"]
    if not years:
        return "Experiencia: sin experiencia"
    shown = f"{years:g} {'año' if years == 1 else 'años'}"
    return "Experiencia: " + (f"{shown} ({', '.join(platforms)})" if platforms else shown)


_CARD_AVAILABILITY = {"full_time": "tiempo completo", "part_time": "medio tiempo", "weekends": "fines de semana"}
_CARD_SCHEDULE = {"morning": "mañana", "afternoon": "tarde", "evening": "noche", "flexible": "flexible"}

RECRUITER = RecruiterTexts(
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

SAZON = ScreeningSpec(
    role="delivery-driver",
    pack=PACK,
    recruiter=RECRUITER,
    title_field=Field.NAME,
    card_order=(Field.LICENSE, Field.EXPERIENCE, Field.AVAILABILITY, Field.SCHEDULE, Field.START_DATE),
    fields=(
        FieldSpec(Field.NAME, ask=bi("¿Cómo te llamas? Necesito tu nombre y apellido.",
                                     "What's your full name, first and last?"),
                  what=bi("tu nombre y apellido", "your first and last name"),
                  label="nombre", not_provided="su nombre",
                  validate=lambda value, today: validators.validate_name(value),
                  same=lambda old, new: validators.fold(old) == validators.fold(new),
                  read=read_attribute("name"), schema={"name": (str | None, None)},
                  prompt="- name: full name as written"),
        FieldSpec(Field.EXPERIENCE,
                  ask=bi("¿Tienes experiencia repartiendo? Dime cuántos años y en qué plataforma.",
                         "Do you have delivery experience? Tell me how many years and on which platform."),
                  what=bi("tus años de experiencia repartiendo (puede ser 0) y la plataforma",
                          "your years of delivery experience (0 is fine) and the platform"),
                  label="experiencia", not_provided="su experiencia",
                  validate=lambda value, today: _experience(value),
                  same=lambda old, new: old["years"] == new["years"] and set(old["platforms"]) == set(new["platforms"]),
                  read=_read_experience, partial=lambda value: {"years": value[0], "platforms": value[1]},
                  decode_candidate=tuple, describe=_describe_experience, card=_card_experience,
                  schema={"experience_years": (float | None, None), "platforms": (list[str], [])},
                  prompt="- experience_years: number of years of delivery experience (0 if none)\n"
                         "- platforms: delivery platforms mentioned, as written (e.g. Glovo, Uber Eats)"),
        FieldSpec(Field.AVAILABILITY,
                  ask=bi("¿Qué disponibilidad tienes: tiempo completo, medio tiempo o fines de semana?",
                         "What's your availability: full-time, part-time or weekends?"),
                  what=bi("tu disponibilidad (tiempo completo, medio tiempo o fines de semana)",
                          "your availability (full-time, part-time or weekends)"),
                  label="disponibilidad", not_provided="su disponibilidad",
                  validate=lambda value, today: checks.validate_availability(value),
                  same=lambda old, new: set(old) == set(new),
                  read=read_attribute("availability", empty_is_missing=True), describe=_describe_availability,
                  card=lambda value: "Disponibilidad: " + ", ".join(_CARD_AVAILABILITY[a] for a in value),
                  schema={"availability": (list[Literal["full_time", "part_time", "weekends"]], [])},
                  prompt='- availability: any of "full_time", "part_time", "weekends"'),
        FieldSpec(Field.SCHEDULE,
                  ask=bi("¿Qué horario prefieres: mañana, tarde, noche o flexible?",
                         "Which schedule do you prefer: morning, afternoon, evening or flexible?"),
                  what=bi("tu horario preferido (mañana, tarde, noche o flexible)",
                          "your preferred schedule (morning, afternoon, evening or flexible)"),
                  label="horario preferido", not_provided="su horario preferido",
                  validate=lambda value, today: checks.validate_schedule(value),
                  read=read_attribute("schedule"), describe=_describe_schedule,
                  card=lambda value: "Horario preferido: " + _CARD_SCHEDULE[value],
                  schema={"schedule": (Literal["morning", "afternoon", "evening", "flexible"] | None, None)},
                  prompt='- schedule: one of "morning", "afternoon", "evening", "flexible"'),
        FieldSpec(Field.START_DATE, ask=bi("¿Cuándo podrías empezar?", "When could you start?"),
                  what=bi("cuándo puedes empezar", "when you can start"),
                  label="fecha de inicio", not_provided="su fecha de inicio",
                  validate=checks.validate_start_date, read=_read_start_date,
                  decode_value=_date_from_json, decode_candidate=_date_from_json,
                  card=lambda value: "Inicio: " + value,
                  schema={"start_date": (StartDate | None, None)},
                  prompt='- start_date: {"iso": "YYYY-MM-DD"} for an exact date, else {"now": true}, {"in_days": n} or '
                         '{"in_weeks": n}, {"in_months": n}, or {"weekday": 0-6} (Monday=0) for "next Monday" or '
                         '"el lunes". Never do date arithmetic yourself.'),
        FieldSpec(Field.CITY, ask=bi("¿En qué ciudad o zona vives?", "Which city or area do you live in?"),
                  what=bi("la ciudad o zona donde vives", "the city or area where you live"),
                  label="ciudad", not_provided="su ciudad",
                  confirm_rejection=bi("Solo para confirmar: ¿es correcto que vives en {city}?",
                                       "Just to confirm: is it right that you live in {city}?"),
                  read=read_attribute("city"), schema={"city": (str | None, None)},
                  prompt="- city: the city or zone exactly as written, never mapped or corrected"),
        FieldSpec(Field.LICENSE, ask=bi("¿Tienes licencia de conducir?", "Do you have a driver's license?"),
                  what=bi("si tienes licencia de conducir (sí o no)", "whether you have a driver's license (yes or no)"),
                  label="licencia", not_provided="si tiene licencia de conducir",
                  validate=lambda value, today: checks.validate_license(value),
                  rejects=lambda value: value is False, read=read_attribute("has_license"),
                  confirm_rejection=bi("Solo para confirmar: ¿es correcto que no tienes licencia de conducir?",
                                       "Just to confirm: is it right that you don't have a driver's license?"),
                  describe=_describe_license, card=lambda value: "Licencia: " + ("sí" if value else "no"),
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
             summary="no tiene licencia de conducir"),
        Rule(Reason.OUT_OF_AREA, applies=lambda screening: screening.out_of_area,
             close=bi("Por ahora no operamos en tu zona, así que no puedo seguir con el proceso automático. "
                      "Un reclutador puede revisar tu caso si hay algún error. Gracias por tu interés.",
                      "We don't operate in your area yet, so I can't continue with the automated process. "
                      "A recruiter can review your case if something is wrong. Thanks for your interest."),
             summary="fuera de la zona de servicio"),
    ),
    area_field=Field.CITY,
    # A country or state written after the place ("Madrid, España") is dropped; any other suffix is kept.
    place_qualifiers=("espana", "spain", "mexico", "jalisco", "nuevo leon", "comunidad de madrid", "cataluna",
                      "catalunya", "comunitat valenciana", "estado de mexico", "edomex"),
)

Extraction = SAZON.extraction_model
SYSTEM = build_system_prompt(SAZON)
