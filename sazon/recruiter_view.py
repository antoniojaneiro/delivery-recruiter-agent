"""What the recruiter dashboard decides, as plain functions so they are testable without Streamlit (D63).
The words the dashboard shows belong to the client; this module only filters, pages and counts."""
import re

from sazon.model import NO_CONSENT, Outcome, RecruiterStatus
from sazon.spec import ScreeningSpec
from sazon.store import Record
from sazon.validators import fold

PAGE_SIZE = 50


def escape_markdown(text: str) -> str:
    """Candidate-written text shown through Markdown (a heading, a warning) must not become a link or image."""
    return re.sub(r"([\\`*_{}\[\]()#+!<>|~])", r"\\\1", text)


def page_of(items: list, page: int, size: int = PAGE_SIZE) -> tuple[list, int, int]:
    """One page of a list: (the items, how many pages there are, the page number actually used)."""
    pages = max(1, -(-len(items) // size))
    page = min(max(int(page), 1), pages)
    return items[(page - 1) * size: page * size], pages, page


def _plain(text: str) -> str:
    """Lower case, no accents, and hyphens or apostrophes read as spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text)).split())


def matches(record: Record, search: str, spec: ScreeningSpec) -> bool:
    """The search looks in the candidate's id, the answer that titles the summary and the area answer."""
    needle = _plain(search)
    if not needle:
        return True
    shown = [record.extracted.get(key) or "" for key in (spec.title_field, spec.area_field) if key]
    return needle in _plain(" ".join([record.candidate_id, *shown]))


def needs_review(record: Record) -> bool:
    """An automated close nobody has looked at yet (D52): the agent rejected the candidate, or ended the chat for
    off-topic messages. Declined consent is the candidate's own choice, so it is not in the queue."""
    return (record.outcome in (Outcome.DISQUALIFIED, Outcome.ENDED_OFF_TOPIC)
            and NO_CONSENT not in record.reasons
            and record.status == RecruiterStatus.NEW)


def filter_records(records: list[Record], outcomes: list[str], statuses: list[str], search: str,
                   spec: ScreeningSpec, review_only: bool = False) -> list[Record]:
    return [r for r in records
            if (not review_only or needs_review(r))
            and (not outcomes or r.outcome in outcomes)
            and (not statuses or r.status in statuses)
            and matches(r, search, spec)]


def kpis(records: list[Record]) -> dict[str, int]:
    return {
        "total": len(records),
        "to_review": sum(1 for r in records if needs_review(r)),
        "to_contact": sum(1 for r in records if r.outcome == Outcome.QUALIFIED and r.status == RecruiterStatus.NEW
                         and r.booking is None),
        "blocked": sum(1 for r in records if r.outcome == Outcome.BLOCKED),
        "stalled": sum(1 for r in records if r.outcome == Outcome.STALLED),
    }
