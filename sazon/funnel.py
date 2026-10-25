"""Funnel analytics (D58): how far applicants get, where they stop, and how many reach a recruiter.
It only counts what the chat already stores, so it needs no extra tracking."""
from collections import Counter
from dataclasses import dataclass

from sazon.model import Outcome, Reason
from sazon.screening import FIELD_ORDER
from sazon.store import Record
from sazon.summary import FIELD_LABEL

OPEN_OUTCOMES = (Outcome.IN_PROGRESS, Outcome.STALLED, Outcome.BLOCKED)


@dataclass(frozen=True)
class Funnel:
    total: int
    consented: int
    qualified: int
    booked: int
    stages: list[tuple[str, int]]
    outcomes: dict[str, int]
    reasons: dict[str, int]
    stopped_at: dict[str, int]
    rates: dict[str, float]


def _share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def build_funnel(records: list[Record]) -> Funnel:
    total = len(records)
    consented = sum(1 for r in records if r.state.get("consent") is True)
    answered = {field: sum(1 for r in records if field in r.extracted) for field in FIELD_ORDER}
    qualified = sum(1 for r in records if r.outcome == Outcome.QUALIFIED)
    booked = sum(1 for r in records if r.booking is not None)
    stages = [("Empezaron", total), ("Dieron su consentimiento", consented)]
    stages += [(f"Respondieron: {FIELD_LABEL[field]}", answered[field]) for field in FIELD_ORDER]
    stages += [("Cualificaron", qualified), ("Reservaron una llamada", booked)]

    stopped = Counter()
    for r in records:
        if r.outcome not in OPEN_OUTCOMES:
            continue
        if r.state.get("consent") is not True:
            stopped["consentimiento"] += 1
            continue
        missing = [f for f in FIELD_ORDER if f not in r.extracted]
        if missing:
            stopped[FIELD_LABEL[missing[0]]] += 1

    closed_by_agent = sum(1 for r in records if r.outcome == Outcome.ENDED_OFF_TOPIC or (
        r.outcome == Outcome.DISQUALIFIED and Reason.NO_CONSENT not in r.reasons))
    rates = {
        "consent": _share(consented, total),
        "qualified": _share(qualified, total),
        "booked_of_qualified": _share(booked, qualified),
        "closed_by_agent": _share(closed_by_agent, total),
    }
    return Funnel(total, consented, qualified, booked, stages,
                  dict(Counter(r.outcome for r in records if r.outcome)),
                  dict(Counter(code for r in records for code in r.reasons)), dict(stopped), rates)
