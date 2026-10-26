"""The recruiter's summary card (D46). Built by code from the saved, validated data: it never repeats
the candidate's own words and never says anything about the person beyond the facts they gave."""
from sazon.model import EventType, Field, Language, Outcome, Reason
from sazon.screening import Screening

OUTCOME_LABEL = {
    Outcome.IN_PROGRESS: "En curso",
    Outcome.QUALIFIED: "Cualificado",
    Outcome.DISQUALIFIED: "Descartado por el agente",
    Outcome.BLOCKED: "Bloqueado",
    Outcome.STALLED: "Sin respuesta",
    Outcome.ENDED_OFF_TOPIC: "Terminó fuera de tema",
    Outcome.WITHDRAWN: "Se retiró",
}
FIELD_LABEL = {
    Field.NAME: "nombre", Field.EXPERIENCE: "experiencia", Field.AVAILABILITY: "disponibilidad",
    Field.SCHEDULE: "horario preferido", Field.START_DATE: "fecha de inicio", Field.CITY: "ciudad",
    Field.LICENSE: "licencia",
}
_NOT_PROVIDED = {
    Field.NAME: "su nombre", Field.EXPERIENCE: "su experiencia", Field.AVAILABILITY: "su disponibilidad",
    Field.SCHEDULE: "su horario preferido", Field.START_DATE: "su fecha de inicio", Field.CITY: "su ciudad",
    Field.LICENSE: "si tiene licencia de conducir",
}
_AVAILABILITY = {"full_time": "tiempo completo", "part_time": "medio tiempo", "weekends": "fines de semana"}
_SCHEDULE = {"morning": "mañana", "afternoon": "tarde", "evening": "noche", "flexible": "flexible"}
_FLAGS = {"START_DATE_FAR": "Aviso: la fecha de inicio está a más de 12 semanas"}
_LANGUAGE = {Language.ES: "español", Language.EN: "inglés"}
FOOTER = "Resumen automático: la decisión final es del reclutador."


def summarise(screening: Screening) -> str:
    decision = screening.decide()
    data = screening.extracted()
    consented = screening.consent is True
    head = [data.get(Field.NAME) or "Candidato sin nombre"]
    if consented and data.get(Field.CITY):
        head.append(data[Field.CITY])
    head.append(OUTCOME_LABEL[decision.outcome])
    lines = [" · ".join(head)]
    reasons = [_reason(code, data) for code in decision.reasons]
    if reasons:
        lines.append("Motivo: " + "; ".join(reasons))
    if consented:
        lines += _data_lines(data)
        missing = [FIELD_LABEL[f] for f in screening.missing_fields()]
        if missing and decision.outcome not in (Outcome.DISQUALIFIED, Outcome.WITHDRAWN):
            lines.append("Falta: " + ", ".join(missing))
    lines += [_FLAGS[flag] for flag in decision.flags if flag in _FLAGS]
    lines.append(_chat_line(screening))
    lines.append(FOOTER)
    return "\n".join(lines)


def _reason(code: str, data: dict) -> str:
    if code == Reason.NO_CONSENT:
        return "no dio su consentimiento"
    if code == Reason.NO_LICENSE:
        return "no tiene licencia de conducir"
    if code == Reason.OUT_OF_AREA:
        return "fuera de la zona de servicio"
    if code.startswith("BLOCKED_ON_"):
        return "no ha indicado " + _NOT_PROVIDED[Field(code.removeprefix("BLOCKED_ON_").lower())]
    return code


def _data_lines(data: dict) -> list[str]:
    lines = []
    if Field.LICENSE in data:
        lines.append("Licencia: " + ("sí" if data[Field.LICENSE] else "no"))
    if Field.EXPERIENCE in data:
        lines.append("Experiencia: " + _experience(data[Field.EXPERIENCE]))
    if Field.AVAILABILITY in data:
        lines.append("Disponibilidad: " + ", ".join(_AVAILABILITY[a] for a in data[Field.AVAILABILITY]))
    if Field.SCHEDULE in data:
        lines.append("Horario preferido: " + _SCHEDULE[data[Field.SCHEDULE]])
    if Field.START_DATE in data:
        lines.append("Inicio: " + data[Field.START_DATE])
    return lines


def _experience(value: dict) -> str:
    years, platforms = value["years"], value["platforms"]
    if not years:
        return "sin experiencia"
    unit = "año" if years == 1 else "años"
    shown = f"{years:g} {unit}"
    return f"{shown} ({', '.join(platforms)})" if platforms else shown


def _chat_line(screening: Screening) -> str:
    kinds = [kind for kind, _ in screening.events]
    parts = [f"idioma {_LANGUAGE[screening.language]}"]
    clarifications = kinds.count(EventType.FOLLOW_UP)
    if clarifications:
        parts.append(f"{clarifications} {'aclaración' if clarifications == 1 else 'aclaraciones'}")
    if EventType.HUMAN_REQUESTED in kinds:
        parts.append("pidió hablar con una persona")
    if screening.reminder_sent:
        parts.append("recordatorio enviado")
    return "Chat: " + " · ".join(parts)
