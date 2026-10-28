"""What the recruiter dashboard decides and shows, as plain code so it is testable without Streamlit (D63, D70):
filtering, paging, and a `RecruiterView` that gives every screen its labels, cards and rows for one client and
language. The words themselves belong to the client (its text pack and its spec)."""
import re

from screener.language import plain
from screener.model import Language, Outcome, RecruiterStatus
from screener.phrasing import slot_label
from screener.recruiter_rules import NEEDS_REVIEW
from screener.spec import ScreeningSpec
from screener.store import Booking, Record, Slot
from screener.summary import card_for
from screener.ui_texts import UiPack, UiTextError

PAGE_SIZE = 50
TABLE_MAX_ROWS = 10  # a table this many rows tall or more scrolls inside itself
ROW_PX, HEADER_PX, BORDER_PX = 35, 38, 3


def escape_markdown(text: str) -> str:
    """Candidate-written text shown through Markdown (a heading, a warning) must not become a link or image."""
    return re.sub(r"([\\`*_{}\[\]()#+!<>|~])", r"\\\1", text)


def page_of(items: list, page: int, size: int = PAGE_SIZE) -> tuple[list, int, int]:
    """One page of a list: (the items, how many pages there are, the page number actually used)."""
    pages = max(1, -(-len(items) // size))
    page = min(max(int(page), 1), pages)
    return items[(page - 1) * size: page * size], pages, page


def table_height(rows: int) -> int:
    """Pixels for a table of `rows` rows: as tall as its rows up to TABLE_MAX_ROWS, then that height (it scrolls)."""
    return HEADER_PX + min(rows, TABLE_MAX_ROWS) * ROW_PX + BORDER_PX


def refresh_action(seen: int | None, current: int, candidate_open: bool) -> str:
    """What a dashboard that was drawn at revision `seen` does when the database is at `current`: nothing, reload, or
    (when a recruiter has a candidate open, with a note maybe half written) only offer the update."""
    if seen is None or seen == current:
        return "none"
    return "offer" if candidate_open else "reload"


def matches(record: Record, search: str, spec: ScreeningSpec) -> bool:
    """The search looks in the candidate's id, the answer that titles the summary and the area answer."""
    needle = plain(search)
    if not needle:
        return True
    shown = [record.extracted.get(key) or "" for key in (spec.title_field, spec.area_field) if key]
    return needle in plain(" ".join([record.candidate_id, *shown]))


def filter_records(records: list[Record], outcomes: list[str], statuses: list[str], search: str,
                   spec: ScreeningSpec, review_only: bool = False) -> list[Record]:
    return [r for r in records
            if (not review_only or NEEDS_REVIEW.matches(r))
            and (not outcomes or r.outcome in outcomes)
            and (not statuses or r.stage in statuses)
            and matches(r, search, spec)]


# Badge colors follow the meaning: green good, red an agent rejection, orange something stuck, blue open, gray over.
BADGE_COLORS = {"red", "orange", "yellow", "blue", "green", "violet", "gray", "primary"}
OUTCOME_COLOR = {
    Outcome.IN_PROGRESS: "blue", Outcome.QUALIFIED: "green", Outcome.DISQUALIFIED: "red",
    Outcome.BLOCKED: "orange", Outcome.STALLED: "gray", Outcome.ENDED_OFF_TOPIC: "red", Outcome.WITHDRAWN: "gray",
}
STATUS_COLOR = {
    RecruiterStatus.NEW: "gray", RecruiterStatus.CONTACTED: "blue", RecruiterStatus.QUALIFIED: "violet",
    RecruiterStatus.INTERVIEW_SCHEDULED: "orange", RecruiterStatus.HIRED: "green", RecruiterStatus.REJECTED: "red",
    RecruiterStatus.UNREACHABLE: "gray",
}

# The keys of the client's text pack that the recruiter screens use (a missing one is refused when the view is built).
REQUIRED_TEXT_KEYS = (
    "col.id", "col.name", "col.city", "col.agent", "col.recruiter", "col.assigned", "col.call", "col.updated",
    "slot.booked", "slot.recruiters_only", "slot.free", "slot.no_name", "error.gone", "error.generic",
    *(f"status.{status.value}" for status in RecruiterStatus),
)


class RecruiterView:
    """What the recruiter screens show for one client in one language. The screens ask it for every label, card and
    row, so nothing on a screen picks a language or a client by itself."""

    def __init__(self, client, pack: UiPack, language: Language | None = None):
        missing = [key for key in REQUIRED_TEXT_KEYS if key not in pack.texts]
        if missing:
            raise UiTextError("the text pack lacks " + ", ".join(missing))
        self.client, self.pack = client, pack
        self.language = language or pack.languages[0]

    def text(self, key: str, **values) -> str:
        return self.pack.get(key, self.language, **values)

    def status_label(self, status) -> str:
        return self.text(f"status.{RecruiterStatus(status).value}")

    def outcome_label(self, outcome) -> str:
        return self.client.spec.recruiter_texts(self.language).outcome_labels.get(outcome, str(outcome or ""))

    def country_label(self, country: str) -> str:
        key = f"country.{country}"
        return self.text(key) if key in self.pack.texts else country

    def no_name(self) -> str:
        return self.text("slot.no_name")

    def name_of(self, record: Record) -> str:
        return record.extracted.get(self.client.spec.title_field) or self.no_name()

    def card(self, record: Record) -> str:
        """The summary card in this language, rebuilt from the saved state (the saved one is the audit snapshot)."""
        return card_for(record, self.client, self.language)

    def call_label(self, booking: Booking | None) -> str:
        if booking is None:
            return ""
        return f"{slot_label(booking.starts_at, self.language)} ({self.country_label(booking.country)})"

    def slot_state(self, slot: Slot, booked_name: str | None, now) -> str:
        """Free, booked, or free but no longer offered to candidates (today or earlier)."""
        if slot.candidate_id:
            return self.text("slot.booked", name=booked_name or self.no_name(), id=slot.candidate_id)
        calendar = self.client.calendar
        if not calendar.candidate_may_book(slot.country, slot.starts_at, now):
            return self.text("slot.recruiters_only")
        return self.text("slot.free")

    def explain_error(self, error: Exception) -> str:
        """The message for a refused input, chosen by its code and never by the English text of the error."""
        if isinstance(error, LookupError):
            return self.text("error.gone")
        key = f"error.{getattr(error, 'code', '')}"
        return self.text(key if key in self.pack.texts else "error.generic")

    def table_rows(self, records: list[Record], names: dict[str, str] | None = None) -> list[dict]:
        """`names`: the recruiters' names by email, to show who holds a call by name."""
        spec, names = self.client.spec, names or {}
        return [{
            self.text("col.id"): r.candidate_id,
            self.text("col.name"): self.name_of(r),
            self.text("col.city"): r.extracted.get(spec.area_field) or "",
            self.text("col.agent"): self.outcome_label(r.outcome),
            self.text("col.recruiter"): self.status_label(r.stage),
            self.text("col.assigned"): names.get(r.assignee, r.assignee or ""),
            self.text("col.call"): self.call_label(r.booking),
            self.text("col.updated"): r.updated_at.strftime("%Y-%m-%d %H:%M"),
        } for r in records]

    def badge_columns(self) -> dict[str, tuple[list[str], list[str]]]:
        """For the table's two status columns: every label a cell can hold and its badge color, in the same order."""
        return {
            self.text("col.agent"): ([self.outcome_label(o) for o in Outcome], [OUTCOME_COLOR[o] for o in Outcome]),
            self.text("col.recruiter"): ([self.status_label(s) for s in RecruiterStatus],
                                         [STATUS_COLOR[s] for s in RecruiterStatus]),
        }

    def badge_rows(self, rows: list[dict]) -> list[dict]:
        """The same rows with the status cells as one-item lists, which is what a badge column shows."""
        columns = self.badge_columns()
        return [{key: [value] if key in columns and value else value for key, value in row.items()} for row in rows]
