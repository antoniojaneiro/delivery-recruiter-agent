import json
from datetime import datetime

from sazon.screening import Screening
from sazon.store import Store


def load(store: Store, candidate_id: str, areas: dict[str, list[str]]) -> Screening:
    record = store.get(candidate_id)
    if record is None or not record.state:
        return Screening(areas)
    return Screening.from_state(areas, record.state)


def commit(store: Store, candidate_id: str, screening: Screening, now: datetime,
           messages: list[tuple[str, str]] = ()) -> None:
    decision = screening.decide()
    previous = store.get(candidate_id)
    events = [(str(kind), detail) for kind, detail in screening.pending_events()]
    if previous is None or previous.outcome != decision.outcome:
        events.append(("decision", json.dumps({
            "outcome": str(decision.outcome), "reasons": decision.reasons, "flags": decision.flags,
        })))
    synced_before = screening.events_synced
    screening.mark_events_synced()
    try:
        store.commit_turn(candidate_id, now, screening.to_state(), screening.extracted(),
                          str(decision.outcome), events, list(messages),
                          reasons=decision.reasons, flags=decision.flags)
    except Exception:
        screening.events_synced = synced_before
        raise
