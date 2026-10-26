import json
from datetime import datetime

from screener.client import Client
from screener.screening import Screening
from screener.store import Store
from screener.summary import summarise


def load(store: Store, candidate_id: str, client: Client) -> Screening:
    record = store.get(candidate_id)
    if record is None or not record.state:
        screening = Screening(client.areas, client.spec)
    else:
        screening = Screening.from_state(client.areas, record.state, client.spec)
    screening.version = record.version if record else None
    return screening


def commit(store: Store, candidate_id: str, screening: Screening, now: datetime,
           messages: list[tuple[str, str]] = (), outbox: list[str] = ()) -> None:
    decision = screening.decide()
    previous = store.get(candidate_id)
    with screening.syncing_events() as new_events:
        events = [(str(kind), detail) for kind, detail in new_events]
        if previous is None or previous.outcome != decision.outcome:
            events.append(("decision", json.dumps({
                "outcome": str(decision.outcome), "reasons": decision.reasons, "flags": decision.flags,
            })))
        screening.version = store.commit_turn(candidate_id, now, screening.to_state(), screening.extracted(),
                          str(decision.outcome), events, list(messages),
                          reasons=decision.reasons, flags=decision.flags, summary=summarise(screening),
                          expected_version=screening.version, outbox=list(outbox))
