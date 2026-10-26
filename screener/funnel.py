"""Funnel analytics (D58): how far applicants get, where they stop, and how many reach a recruiter.
It only counts what the chat already stores, so it needs no extra tracking."""
from dataclasses import dataclass

from screener.model import Language
from screener.spec import ScreeningSpec
from screener.store import Store


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


def build_funnel(store: Store, spec: ScreeningSpec, language: Language | None = None) -> Funnel:
    texts = spec.recruiter_texts(language)

    def label(key: str) -> str:
        return spec.say(spec.field(key).label, language)

    counts = store.funnel_counts(spec.keys)
    total, consented, qualified, booked = counts["total"], counts["consented"], counts["qualified"], counts["booked"]
    stages = [(texts.started, total), (texts.consented, consented)]
    stages += [(texts.answered.format(label=label(key)), counts["answered"][key]) for key in spec.keys]
    stages += [(texts.qualified, qualified), (texts.booked, booked)]
    stopped = {(texts.consent_stage if key == "" else label(key)): n for key, n in counts["stopped"].items()}
    rates = {
        "consent": _share(consented, total),
        "qualified": _share(qualified, total),
        "booked_of_qualified": _share(booked, qualified),
        "closed_by_agent": _share(counts["closed_by_agent"], total),
    }
    return Funnel(total, consented, qualified, booked, stages, counts["outcomes"], counts["reasons"], stopped, rates)
