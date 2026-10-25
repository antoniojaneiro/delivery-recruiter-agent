"""What the recruiter dashboard shows, as plain functions so they are testable without Streamlit."""
import re

from sazon.model import Language, Outcome, Reason, RecruiterStatus
from sazon.phrasing import slot_label
from sazon.model import Language
from sazon.store import Booking, Record, Slot
from sazon import slot_time
from sazon.summary import OUTCOME_LABEL
from sazon.validators import fold

STATUS_LABEL = {
    RecruiterStatus.NEW: "Nuevo",
    RecruiterStatus.CONTACTED: "Contactado",
    RecruiterStatus.INTERVIEW_SCHEDULED: "Entrevista programada",
    RecruiterStatus.HIRED: "Contratado",
    RecruiterStatus.REJECTED: "Rechazado",
    RecruiterStatus.UNREACHABLE: "No localizable",
}
NO_NAME = "(sin nombre)"
COUNTRY_LABEL = {"ES": "España", "MX": "México"}


def call_label(booking: Booking | None) -> str:
    """The booked call in the recruiter's language, with the country whose clock it is."""
    if booking is None:
        return ""
    return f"{slot_label(booking.starts_at, Language.ES)} ({COUNTRY_LABEL.get(booking.country, booking.country)})"


def slot_state(slot: Slot, booked_name: str | None, now) -> str:
    """Free, booked, or free but too close to be offered or booked (the agent needs 2 hours' notice)."""
    if slot.candidate_id:
        return f"Reservado: {booked_name or '(sin nombre)'} ({slot.candidate_id})"
    if not slot_time.has_enough_notice(slot.country, slot.starts_at, now):
        return "Ya no se ofrece (faltan menos de 2 horas)"
    return "Libre"


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


def _plain(text: str) -> str:
    """Lower case, no accents, and hyphens or apostrophes read as spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text)).split())


def matches(record: Record, search: str) -> bool:
    needle = _plain(search)
    if not needle:
        return True
    haystack = _plain(" ".join([record.candidate_id, record.extracted.get("name") or "",
                                record.extracted.get("city") or ""]))
    return needle in haystack


def needs_review(record: Record) -> bool:
    """An automated close nobody has looked at yet (D52): the agent rejected the candidate, or ended the chat for
    off-topic messages. Declined consent is the candidate's own choice, so it is not in the queue."""
    return (record.outcome in (Outcome.DISQUALIFIED, Outcome.ENDED_OFF_TOPIC)
            and Reason.NO_CONSENT not in record.reasons
            and record.status == RecruiterStatus.NEW)


def filter_records(records: list[Record], outcomes: list[str], statuses: list[str], search: str,
                   review_only: bool = False) -> list[Record]:
    return [r for r in records
            if (not review_only or needs_review(r))
            and (not outcomes or r.outcome in outcomes)
            and (not statuses or r.status in statuses)
            and matches(r, search)]


def kpis(records: list[Record]) -> dict[str, int]:
    return {
        "total": len(records),
        "to_review": sum(1 for r in records if needs_review(r)),
        "to_contact": sum(1 for r in records if r.outcome == Outcome.QUALIFIED and r.status == RecruiterStatus.NEW
                         and r.booking is None),
        "blocked": sum(1 for r in records if r.outcome == Outcome.BLOCKED),
        "stalled": sum(1 for r in records if r.outcome == Outcome.STALLED),
    }
