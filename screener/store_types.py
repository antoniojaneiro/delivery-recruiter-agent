"""What the store hands out: records, events, slots, and the two errors it raises."""
from dataclasses import dataclass
from datetime import datetime

from screener.model import RecruiterStatus

AGENT = "agent"
NO_CHECK = object()  # commit_turn without a version check (tests and tools that own the whole record)


class InputError(ValueError):
    """A recruiter's input was refused. `code` says why, so the pages need not read an English message."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class ConflictError(Exception):
    """The candidate's record changed, or was erased, after this copy was loaded."""


@dataclass(frozen=True)
class CvFile:
    """The PDF a candidate uploaded (D71)."""
    data: bytes
    size: int
    sha256: str
    uploaded_at: datetime


@dataclass(frozen=True)
class Message:
    role: str
    text: str
    at: datetime


@dataclass(frozen=True)
class Record:
    candidate_id: str
    state: dict
    extracted: dict
    summary: str | None
    outcome: str | None
    updated_at: datetime
    reasons: list
    flags: list
    status: RecruiterStatus
    assignee: str | None
    booking: "Booking | None" = None
    version: int = 0


@dataclass(frozen=True)
class Event:
    type: str
    detail: str
    at: datetime
    actor: str = AGENT


@dataclass(frozen=True)
class RecruiterRecord:
    status: RecruiterStatus
    assignee: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class Slot:
    id: int
    country: str
    starts_at: datetime  # wall-clock time in the country's own zone
    recruiter: str | None
    candidate_id: str | None
    cancelled: bool


@dataclass(frozen=True)
class Booking:
    slot_id: int
    country: str
    starts_at: datetime
    recruiter: str | None


@dataclass(frozen=True)
class OutboxEntry:
    id: int
    candidate_id: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class AdminEntry:
    at: datetime
    actor: str
    action: str
    detail: str


@dataclass(frozen=True)
class Note:
    author: str
    text: str
    at: datetime


def local_naive(moment: datetime) -> datetime:
    """Every time the store keeps is naive local time (this machine's), whatever the caller passes."""
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def stamp(now: datetime) -> str:
    return local_naive(now).isoformat()


def parse_stamp(text: str) -> datetime:
    return local_naive(datetime.fromisoformat(text))


@dataclass(frozen=True)
class Call:
    """A booked call, as the calendar sees it: whose, when, and with which recruiter."""
    slot_id: int
    candidate_id: str
    country: str
    starts_at: datetime
    recruiter: str


@dataclass(frozen=True)
class Claim:
    """The answer to claiming a message id: `new` (do the work), `busy` (someone is doing it now) or `done` (the
    stored `reply` is the answer)."""
    state: str
    reply: str | None = None
