"""What the engine decided to say, apart from how it is said (D70). `Screening` and the call-booking code build a
Directive; `phrasing` turns it into words. Nothing here knows a language or a client."""
from dataclasses import dataclass, field as dc_field
from enum import StrEnum

from screener.model import Outcome

NOTICE_NAMES = ("human", "pay", "changed", "kept", "offtopic")  # the client's fixed notices, by name


class Kind(StrEnum):
    ASK = "ask"
    FOLLOW_UP = "follow_up"
    CONFIRM_AREA = "confirm_area"
    CONFIRM_REJECTION = "confirm_rejection"
    BLOCKED = "blocked"
    CONFIRM_CHANGE = "confirm_change"
    OFFER_SLOTS = "offer_slots"
    SLOT_BOOKED = "slot_booked"
    ALREADY_BOOKED = "already_booked"
    REMINDER = "reminder"
    CLOSE = "close"
    TECHNICAL_ERROR = "technical_error"
    CV_OFFER = "cv_offer"  # the optional upload, said once after consent
    CV_READ = "cv_read"  # what was taken from the CV, listed in `options`


@dataclass(frozen=True)
class Directive:
    kind: Kind
    field: str | None = None
    reason: str = ""
    suggestion: str | None = None
    outcome: Outcome | None = None
    reasons: list[str] = dc_field(default_factory=list)
    options: list[str] = dc_field(default_factory=list)
    label: str | None = None
    notices: tuple[str, ...] = ()  # fixed sentences said before the question: a person, pay, a change made...
    repeat: bool = False  # a closing already sent once: say it shortly instead of word for word

    def __post_init__(self):
        unknown = [name for name in self.notices if name not in NOTICE_NAMES]
        if unknown:
            raise ValueError(f"unknown notice: {', '.join(unknown)}")
