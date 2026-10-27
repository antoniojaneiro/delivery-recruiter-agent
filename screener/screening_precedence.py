"""What the agent says first when several things wait at once (D63). The order is the rule: a closed chat only closes,
then a rejection waits for its yes or no, then a near-miss place, then a changed answer, then a blocked field, then an
unclear answer to ask again, and last the next question."""
from dataclasses import dataclass

from screener.directive import Directive, Kind


@dataclass(frozen=True)
class Waiting:
    is_open: bool
    rejection: str | None  # a field whose rejecting answer waits for the candidate's confirmation
    rejection_subject: str | None  # the candidate's own words for it, shown back to them
    area: str | None  # a near-miss place waiting for "do you mean ...?"
    change: tuple | None  # (field, candidate answer, old in words, new in words)
    blocked_on: str | None
    next_field: str | None


def directive_for(waiting: Waiting, unclear: tuple[str, str] | None, close: Directive) -> Directive:
    if not waiting.is_open:
        return close
    if waiting.rejection:
        return Directive(Kind.CONFIRM_REJECTION, field=waiting.rejection, suggestion=waiting.rejection_subject)
    if waiting.area:
        return Directive(Kind.CONFIRM_AREA, suggestion=waiting.area)
    if waiting.change:
        field, _, old_text, new_text = waiting.change
        return Directive(Kind.CONFIRM_CHANGE, field=field, options=[old_text, new_text])
    if waiting.blocked_on:
        return Directive(Kind.BLOCKED, field=waiting.blocked_on)
    if unclear:
        return Directive(Kind.FOLLOW_UP, field=unclear[0], reason=unclear[1])
    return Directive(Kind.ASK, field=waiting.next_field)
