"""The save cycle of a candidate's screening (D70): load it, let the caller change it, save it, and decide what a
lost race means. A caller says what to change (`work`) and what to do when somebody else saved first."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from screener import session
from screener.client import Client
from screener.screening import Screening
from screener.store import ConflictError, Store

RAISE, RETRY_ONCE, SKIP = "raise", "retry_once", "skip"  # what to do when the record changed after it was loaded


@dataclass
class Turn:
    """What the work produces: the value for the caller and what to save with the screening."""
    value: Any = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    outbox: list[str] = field(default_factory=list)
    save: bool = True  # False: nothing changed that is worth saving (the caller only wanted to look)
    cv: bytes | None = None  # a PDF uploaded in this turn, saved with it


def run(store: Store, client: Client, candidate_id: str, now: datetime, work: Callable[[Screening], Turn],
        on_conflict: str = RAISE, default: Any = None) -> Any:
    """`work(screening)` changes the loaded screening and returns a Turn; its messages are saved with it and its
    value is returned. If the record changed (or was erased) after it was loaded, `on_conflict` decides: RAISE lets
    the ConflictError through, RETRY_ONCE loads a fresh copy and calls `work` again (and raises if it loses again),
    SKIP returns `default`. A candidate erased meanwhile is never recreated and is never retried."""
    attempts = 2 if on_conflict == RETRY_ONCE else 1
    for attempt in range(attempts):
        screening = session.load(store, candidate_id, client)
        turn = work(screening)
        if not turn.save:
            return turn.value
        try:
            session.commit(store, candidate_id, screening, now, messages=turn.messages, outbox=turn.outbox,
                           cv=turn.cv)
            return turn.value
        except ConflictError:
            erased = screening.version is not None and store.get(candidate_id) is None
            if erased or attempt == attempts - 1:
                if on_conflict == SKIP:
                    return default
                raise
    raise AssertionError("unreachable")
