"""The words Grupo Sazón's recruiter dashboard shows, in the language the recruiter picked (D63, D66).
Filtering, paging and counting are the engine's; the texts are in `ui_pack`."""
from screener.model import Language, RecruiterStatus
from screener.phrasing import slot_label
from screener.screening import Screening
from screener.store import Booking, Record, Slot
from screener.summary import summarise
from sazon.client import SAZON_CLIENT
from sazon.spec import RECRUITER
from sazon.ui_pack import PACK

ES = Language.ES


def status_label(status, language: Language = ES) -> str:
    return PACK.get(f"status.{RecruiterStatus(status).value}", language)


def outcome_label(outcome, language: Language = ES) -> str:
    labels = RECRUITER.get(language, RECRUITER[ES]).outcome_labels
    return labels.get(outcome, str(outcome or ""))


def country_label(country: str, language: Language = ES) -> str:
    key = f"country.{country}"
    return PACK.get(key, language) if key in PACK.texts else country


def no_name(language: Language = ES) -> str:
    return PACK.get("slot.no_name", language)


# Spanish views of the same labels, for code and tests that want a plain dictionary.
STATUS_LABEL = {status: status_label(status) for status in RecruiterStatus}
OUTCOME_LABEL = RECRUITER[ES].outcome_labels
NO_NAME = no_name()
COUNTRY_LABEL = {code: country_label(code) for code in ("ES", "MX")}


def call_label(booking: Booking | None, language: Language = ES) -> str:
    """The booked call in the recruiter's language, with the country whose clock it is."""
    if booking is None:
        return ""
    return f"{slot_label(booking.starts_at, language)} ({country_label(booking.country, language)})"


def slot_state(slot: Slot, booked_name: str | None, now, calendar, language: Language = ES) -> str:
    """Free, booked, or free but too close to be offered or booked (the agent needs some hours' notice)."""
    if slot.candidate_id:
        return PACK.get("slot.booked", language, name=booked_name or no_name(language), id=slot.candidate_id)
    if not calendar.has_enough_notice(slot.country, slot.starts_at, now):
        hours = int(calendar.min_notice.total_seconds() // 3600)
        return PACK.get("slot.too_close", language, hours=hours)
    return PACK.get("slot.free", language)


def explain_error(error: Exception, language: Language = ES) -> str:
    """The message for a refused input, chosen by its code and never by the English text of the error."""
    if isinstance(error, LookupError):
        return PACK.get("error.gone", language)
    key = f"error.{getattr(error, 'code', '')}"
    return PACK.get(key if key in PACK.texts else "error.generic", language)


def name_of(record: Record, language: Language = ES) -> str:
    return record.extracted.get("name") or no_name(language)


def table_rows(records: list[Record], language: Language = ES) -> list[dict]:
    return [{
        PACK.get("col.id", language): r.candidate_id,
        PACK.get("col.name", language): name_of(r, language),
        PACK.get("col.city", language): r.extracted.get("city") or "",
        PACK.get("col.agent", language): outcome_label(r.outcome, language),
        PACK.get("col.recruiter", language): status_label(r.status, language),
        PACK.get("col.assigned", language): r.assignee or "",
        PACK.get("col.call", language): call_label(r.booking, language),
        PACK.get("col.updated", language): r.updated_at.strftime("%Y-%m-%d %H:%M"),
    } for r in records]


def card_of(record: Record, language: Language = ES) -> str:
    """The summary card in the recruiter's language, rebuilt from the saved state (a read, never a write). The card
    saved with the candidate stays the audit snapshot. A record with no state (erased) shows what was saved."""
    if not record.state:
        return record.summary or ""
    screening = Screening.from_state(SAZON_CLIENT.areas, record.state, SAZON_CLIENT.spec)
    return summarise(screening, language)
