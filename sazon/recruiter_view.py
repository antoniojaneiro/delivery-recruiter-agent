"""The words Grupo Sazón's recruiter dashboard shows, in Spanish (D63). Filtering, paging and counting are the engine's."""
from screener.model import Language, RecruiterStatus
from screener.phrasing import slot_label
from sazon.spec import RECRUITER
from screener.store import Booking, Record, Slot

STATUS_LABEL = {
    RecruiterStatus.NEW: "Nuevo",
    RecruiterStatus.CONTACTED: "Contactado",
    RecruiterStatus.INTERVIEW_SCHEDULED: "Entrevista programada",
    RecruiterStatus.HIRED: "Contratado",
    RecruiterStatus.REJECTED: "Rechazado",
    RecruiterStatus.UNREACHABLE: "No localizable",
}
OUTCOME_LABEL = RECRUITER[Language.ES].outcome_labels
NO_NAME = "(sin nombre)"
COUNTRY_LABEL = {"ES": "España", "MX": "México"}


def call_label(booking: Booking | None) -> str:
    """The booked call in the recruiter's language, with the country whose clock it is."""
    if booking is None:
        return ""
    return f"{slot_label(booking.starts_at, Language.ES)} ({COUNTRY_LABEL.get(booking.country, booking.country)})"


def slot_state(slot: Slot, booked_name: str | None, now, calendar) -> str:
    """Free, booked, or free but too close to be offered or booked (the agent needs some hours' notice)."""
    if slot.candidate_id:
        return f"Reservado: {booked_name or '(sin nombre)'} ({slot.candidate_id})"
    if not calendar.has_enough_notice(slot.country, slot.starts_at, now):
        hours = int(calendar.min_notice.total_seconds() // 3600)
        return f"Ya no se ofrece (faltan menos de {hours} horas)"
    return "Libre"


_INPUT_ERRORS = {
    "name_required": "Inicia sesión con tu cuenta para registrar acciones.",
    "unknown_status": "Ese estado no existe.",
    "assignee_required": "Escribe a quién se asigna.",
    "note_empty": "La nota no puede estar vacía.",
    "unknown_country": "Ese país no existe.",
    "clock_change": "Esa hora no existe: ese día cambia la hora y se salta de las 02:00 a las 03:00. Elige otra.",
    "too_soon": "Ese horario ya ha pasado o falta muy poco. Elige uno más adelante.",
    "no_calendar": "Este cliente no reserva llamadas.",
}
GONE = "Eso ya no existe: puede que lo hayan borrado o cancelado mientras tanto."


def explain_error(error: Exception) -> str:
    """The Spanish message for a refused input, chosen by its code and never by the English text."""
    if isinstance(error, LookupError):
        return GONE
    return _INPUT_ERRORS.get(getattr(error, "code", ""), "No se pudo guardar. Revisa lo que has escrito.")


def name_of(record: Record) -> str:
    return record.extracted.get("name") or NO_NAME


def table_rows(records: list[Record]) -> list[dict]:
    return [{
        "Id": r.candidate_id,
        "Nombre": name_of(r),
        "Ciudad": r.extracted.get("city") or "",
        "Agente": OUTCOME_LABEL.get(r.outcome, r.outcome or ""),
        "Reclutador": STATUS_LABEL[r.status],
        "Asignado a": r.assignee or "",
        "Llamada": call_label(r.booking),
        "Actualizado": r.updated_at.strftime("%Y-%m-%d %H:%M"),
    } for r in records]
