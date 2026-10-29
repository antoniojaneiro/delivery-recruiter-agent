"""Running a candidate's message exactly once (D75, D93, D94), for every channel that can repeat a request: the HTTP service and
the voice endpoint. The message id is claimed; a resend waits for the first copy, then gets its stored reply. What a channel
does with a refusal, a failure or a wait that ran out (a status code, a spoken apology) is its own, so the result says which."""
import sqlite3
import time
from dataclasses import dataclass
from typing import Callable

CLAIM_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class Ran:
    status: str  # ran | replayed | busy | refused | failed | unrecorded
    reply: str | None = None
    refusal: object = None  # what `before` returned, for "refused"
    error: Exception | None = None  # "failed": what the work raised; "unrecorded": why the reply was not saved


def run_once(store, candidate_id: str, message_id: str, work: Callable[[], str], *, clock, wait: float,
             before: Callable[[], object] | None = None, finish_attempts: int = 1, retry_pause: float = 0.2) -> Ran:
    """`wait`: how long a resend waits for the first copy. `before`: asked once the message is ours; anything but None refuses
    it. A failed or refused message is released, so the same id may be tried again. `finish_attempts`: how hard to try to record
    the reply once the turn is saved (the claim then stays, so a resend waits and the message is not run again)."""
    deadline = time.monotonic() + wait
    while True:
        claim = store.claim_message(candidate_id, message_id, clock())
        if claim.state == "done":
            return Ran("replayed", claim.reply)
        if claim.state == "new":
            break
        if time.monotonic() > deadline:
            return Ran("busy")
        time.sleep(CLAIM_POLL_SECONDS)
    if before is not None and (refusal := before()) is not None:
        store.release_message(candidate_id, message_id)
        return Ran("refused", refusal=refusal)
    try:
        reply = work()
    except Exception as error:  # noqa: BLE001  nothing was saved for this message
        try:
            store.release_message(candidate_id, message_id)
        except sqlite3.OperationalError:
            pass  # a claim nobody finishes is taken over after five minutes
        return Ran("failed", error=error)
    for attempt in range(finish_attempts):
        try:
            store.finish_message(candidate_id, message_id, reply)
            return Ran("ran", reply)
        except sqlite3.OperationalError as error:
            if attempt == finish_attempts - 1:
                return Ran("unrecorded", reply, error=error)
            time.sleep(retry_pause)
    return Ran("ran", reply)
