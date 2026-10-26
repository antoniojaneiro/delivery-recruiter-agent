"""What a screen can show about one candidate: outcome, validated data, the recruiter card, the booked call and the
messages waiting to be sent (D66). It only reads."""
from dataclasses import dataclass

from screener.client import Client
from screener.model import Language
from screener.store import Booking, OutboxEntry, Store
from screener.summary import card_for


@dataclass(frozen=True)
class Inspection:
    outcome: str | None
    reasons: list
    flags: list
    extracted: dict
    card: str
    booking: Booking | None
    queued: list[OutboxEntry]


def inspect(store: Store, client: Client, candidate_id: str, language: Language | None = None) -> Inspection | None:
    record = store.get(candidate_id)
    if record is None:
        return None
    return Inspection(record.outcome, record.reasons, record.flags, record.extracted,
                      card_for(record, client, language), record.booking, store.outbox_pending(candidate_id))
