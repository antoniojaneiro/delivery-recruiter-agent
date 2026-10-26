"""Funnel analytics (D58): how far applicants get, where they stop, and how many reach a recruiter.
It only counts what the chat already stores, so it needs no extra tracking."""
from collections import Counter
from dataclasses import dataclass

from screener.model import NO_CONSENT, Outcome
from screener.spec import ScreeningSpec
from screener.store import Record

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


def build_funnel(records: list[Record], spec: ScreeningSpec) -> Funnel:
    texts = spec.recruiter
    total = len(records)
    consented = sum(1 for r in records if r.state.get("consent") is True)
    answered = {field: sum(1 for r in records if field in r.extracted) for field in spec.keys}
    qualified = sum(1 for r in records if r.outcome == Outcome.QUALIFIED)
    booked = sum(1 for r in records if r.booking is not None)
    stages = [(texts.started, total), (texts.consented, consented)]
    stages += [(texts.answered.format(label=spec.field(field).label), answered[field]) for field in spec.keys]
    stages += [(texts.qualified, qualified), (texts.booked, booked)]

    stopped = Counter()
    for r in records:
        if r.outcome not in OPEN_OUTCOMES:
            continue
        if r.state.get("consent") is not True:
            stopped[texts.consent_stage] += 1
            continue
        missing = [f for f in spec.keys if f not in r.extracted]
        if missing:
            stopped[spec.field(missing[0]).label] += 1

    closed_by_agent = sum(1 for r in records if r.outcome == Outcome.ENDED_OFF_TOPIC or (
        r.outcome == Outcome.DISQUALIFIED and NO_CONSENT not in r.reasons))
    rates = {
        "consent": _share(consented, total),
        "qualified": _share(qualified, total),
        "booked_of_qualified": _share(booked, qualified),
        "closed_by_agent": _share(closed_by_agent, total),
    }
    return Funnel(total, consented, qualified, booked, stages,
                  dict(Counter(r.outcome for r in records if r.outcome)),
                  dict(Counter(code for r in records for code in r.reasons)), dict(stopped), rates)
