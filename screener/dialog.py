"""What the terminal chat and the browser chat both do (D70): start a new candidate and hand over the messages the
reminder job queued. Neither knows how to draw an id or how the outbox is marked."""
import uuid
from datetime import datetime

from screener import turn
from screener.client import Client
from screener.store import Store


def draw_id() -> str:
    return uuid.uuid4().hex[:12]


def new_candidate(store: Store, client: Client, now: datetime) -> tuple[str, str]:
    """A new candidate and the disclosure they are shown first. The id is never one already in use."""
    candidate_id = draw_id()
    while store.get(candidate_id) is not None:  # never merge two applicants into one record
        candidate_id = draw_id()
    return candidate_id, turn.start(store, client, candidate_id, now)


def deliver_queued(store: Store, candidate_id: str | None, now: datetime) -> list[str]:
    """The queued messages for a candidate, marked delivered: a channel with no way to send by itself shows them."""
    pending = store.outbox_pending(candidate_id) if candidate_id else []
    for entry in pending:
        store.mark_delivered(entry.id, now)
    return [entry.text for entry in pending]
