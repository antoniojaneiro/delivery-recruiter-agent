"""What the recruiter dashboard shows, as plain functions so they are testable without Streamlit."""
import re

from sazon.model import Outcome, RecruiterStatus
from sazon.phrasing import slot_label
from sazon.model import Language
from sazon.store import Booking, Record
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


def filter_records(records: list[Record], outcomes: list[str], statuses: list[str], search: str) -> list[Record]:
    return [r for r in records
            if (not outcomes or r.outcome in outcomes)
            and (not statuses or r.status in statuses)
            and matches(r, search)]


def kpis(records: list[Record]) -> dict[str, int]:
    return {
        "total": len(records),
        "to_contact": sum(1 for r in records if r.outcome == Outcome.QUALIFIED and r.status == RecruiterStatus.NEW
                         and r.booking is None),
        "blocked": sum(1 for r in records if r.outcome == Outcome.BLOCKED),
        "stalled": sum(1 for r in records if r.outcome == Outcome.STALLED),
    }
