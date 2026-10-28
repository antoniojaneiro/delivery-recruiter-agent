"""What a recruiter must act on, defined once (D70). A rule answers for one record in Python (`matches`) and for the
whole table in SQL (`sql`, used by the counters), so the table filter, the numbers and the pages cannot disagree.
Only outcomes, a recruiter status and a reason that are named here ever reach the SQL text."""
from dataclasses import dataclass, replace

from screener.model import NO_CONSENT, Outcome, RecruiterStatus


@dataclass(frozen=True)
class Rule:
    outcomes: tuple[Outcome, ...]  # the agent's outcome is one of these
    status: RecruiterStatus | None = None  # the recruiter's status is this one (None: any)
    without_reason: str | None = None  # the agent's reasons do not include this one
    unbooked: bool = False  # no call is booked

    def matches(self, record) -> bool:
        return (record.outcome in self.outcomes
                and (self.status is None or record.status == self.status)
                and (self.without_reason is None or self.without_reason not in record.reasons)
                and (not self.unbooked or record.booking is None))

    def sql(self) -> str:
        """The same rule as a condition over the aliases c (candidates), r (recruiter) and s (the live booking)."""
        parts = ["c.outcome IN (" + ", ".join(f"'{Outcome(o).value}'" for o in self.outcomes) + ")"]
        if self.status is not None:
            parts.append(f"COALESCE(r.status, 'new') = '{RecruiterStatus(self.status).value}'")
        if self.without_reason is not None:
            reason = self.without_reason.replace("'", "''")
            parts.append(f"NOT EXISTS (SELECT 1 FROM json_each(c.reasons) WHERE value = '{reason}')")
        if self.unbooked:
            parts.append("s.id IS NULL")
        return "(" + " AND ".join(parts) + ")"


# The agent closed the chat on its own (not because the candidate declined consent, which is their choice).
AGENT_CLOSED = Rule((Outcome.DISQUALIFIED, Outcome.ENDED_OFF_TOPIC), without_reason=NO_CONSENT)
# ... and no recruiter has looked at it yet (D52).
NEEDS_REVIEW = replace(AGENT_CLOSED, status=RecruiterStatus.NEW)
TO_CONTACT = Rule((Outcome.QUALIFIED,), status=RecruiterStatus.NEW, unbooked=True)
BLOCKED = Rule((Outcome.BLOCKED,))
STALLED = Rule((Outcome.STALLED,))

_CLOSED_BY_RECRUITER = (RecruiterStatus.HIRED, RecruiterStatus.REJECTED, RecruiterStatus.UNREACHABLE)


def closed_by_recruiter(record) -> bool:
    return record.status in _CLOSED_BY_RECRUITER


def can_schedule(record) -> bool:
    """A recruiter may book or move a call for a candidate the agent qualified, unless a recruiter has already closed
    their case (hired, rejected, unreachable). A candidate who ignored the offer is still qualified (D58), so this is
    the one who most needs it. Only qualified candidates are scheduled: a closed case stays with the agent's decision."""
    return record.outcome == Outcome.QUALIFIED and not closed_by_recruiter(record)
