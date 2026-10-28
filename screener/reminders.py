"""The 24-hour reminder job (D35, D38, D58). Run it every few minutes:

    python -m <client>.reminders                  # one pass
    python -m <client>.reminders --every 600      # keep running, one pass every 10 minutes

After 24 hours of silence a candidate gets one reminder; after 24 more hours without a reply they are marked
STALLED. A qualified candidate who ignores the slot offer gets one reminder with the free slots, then is told to write again to book. The terminal chat has nowhere to deliver a message by itself, so the texts are queued in an outbox
(`/inbox` in the chat shows them) for the real channel to send.

It only compares the chat's own timestamps (never the dashboard's), takes `now` as a parameter, does nothing while
applications are closed, and skips a candidate whose record changed while it worked."""
import argparse
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from screener import conversation, slot_flow
from screener.conversation import SKIP, Turn
from screener.client import Client
from screener.llm import NO_MODEL
from screener.model import Outcome
from screener.phrasing import phrase
from screener.screening import Screening
from screener.store import Store
from screener.store_types import local_naive

WATCHED = (Outcome.IN_PROGRESS, Outcome.BLOCKED, Outcome.QUALIFIED)


@dataclass(frozen=True)
class Action:
    candidate_id: str
    kind: str  # "reminder", "stalled", "gave_up_offer" or "error"


@dataclass(frozen=True)
class Sent:
    action: Action
    text: str | None  # what the candidate was sent (None: they were marked stalled, with nothing to say)


def run_once(store: Store, client: Client, now: datetime) -> list[Action]:
    if not store.accepting_applications():
        return []
    now = local_naive(now)
    activity = store.last_activity()
    actions = []
    for record in store.list_candidates():
        last = activity.get(record.candidate_id)
        if record.outcome not in WATCHED or last is None or now - local_naive(last) < client.remind_after:
            continue
        try:
            sent = _remind(store, client, record.candidate_id, now)
            action = sent.action if sent else None
        except Exception:  # noqa: BLE001  one damaged record must not stop the pass for everyone else
            action = Action(record.candidate_id, "error")
        if action:
            actions.append(action)
    return actions


def _remind(store: Store, client: Client, candidate_id: str, now: datetime, skip_wait: bool = False) -> Sent | None:
    last = store.last_activity_of(candidate_id)  # fresh: they may have written since the pass started
    if last is None or (not skip_wait and now - local_naive(last) < client.remind_after):
        return None

    def work(screening: Screening) -> Turn:
        if screening.needs_consent:
            return Turn(None, save=False)  # they have not agreed to anything yet, so they are not contacted again
        if screening.awaiting_slot_choice and not slot_flow.may_choose_time(store, client, candidate_id):
            screening.resolve_slots()  # booked some other way, or a recruiter closed the case: nothing to ask them
            return Turn(None)
        if screening.awaiting_slot_choice:
            kind, directive = slot_flow.on_idle(store, client, screening, now)
        elif screening.is_open:
            directive = screening.on_silence()
            kind = "reminder" if directive else "stalled"
        else:
            return Turn(None, save=False)
        text = phrase(NO_MODEL, client.spec, directive, screening.language) if directive else None  # fixed: no model
        return Turn(Sent(Action(candidate_id, kind), text), messages=[("agent", text)] if text else [],
                    outbox=[text] if text else [])

    # the candidate wrote (or was erased) while we worked: leave them for the next pass
    return conversation.run(store, client, candidate_id, now, work, on_conflict=SKIP)


def wait_a_day(store: Store, client: Client, candidate_id: str, now: datetime) -> str | None:
    """The demo's "wait a day": the job's own step for one candidate, as the job would run it after a day of silence (the
    wait is skipped, everything else is the job's). Returns what they were sent (None: nothing, or they are marked
    stalled). The demo shows the text itself, so it is not left in the outbox for a channel to send again. What is saved
    is stamped with the real time."""
    if store.last_activity_of(candidate_id) is None or not store.accepting_applications():
        return None
    at = local_naive(now)
    sent = _remind(store, client, candidate_id, at, skip_wait=True)
    if sent is None:
        return None
    if sent.text:
        queued = store.outbox_pending(candidate_id)
        if queued:
            store.mark_delivered(queued[-1].id, at)
    return sent.text


def main(client: Client, db_path: Path, prog: str, argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0])
    parser.add_argument("--every", type=int, help="keep running, one pass every N seconds")
    parser.add_argument("--now", help="the moment to act at (ISO format; for tests)")
    args = parser.parse_args(argv)
    store = Store(db_path, calendar=client.calendar)
    while True:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now()
        for action in run_once(store, client, now):
            print(f"{now:%Y-%m-%d %H:%M}  {action.candidate_id}  {action.kind}")
        if not args.every:
            return
        time.sleep(args.every)
