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
            action = _remind(store, client, record.candidate_id, now)
        except Exception:  # noqa: BLE001  one damaged record must not stop the pass for everyone else
            action = Action(record.candidate_id, "error")
        if action:
            actions.append(action)
    return actions


def _remind(store: Store, client: Client, candidate_id: str, now: datetime) -> Action | None:
    last = store.last_activity_of(candidate_id)  # fresh: they may have written since the pass started
    if last is None or now - local_naive(last) < client.remind_after:
        return None

    def work(screening: Screening) -> Turn:
        if screening.needs_consent:
            return Turn(None, save=False)  # they have not agreed to anything yet, so they are not contacted again
        if screening.awaiting_slot_choice:
            kind, directive = slot_flow.on_idle(store, client, screening, now)
        elif screening.is_open:
            directive = screening.on_silence()
            kind = "reminder" if directive else "stalled"
        else:
            return Turn(None, save=False)
        text = phrase(NO_MODEL, client.spec, directive, screening.language) if directive else None  # fixed: no model
        return Turn(Action(candidate_id, kind), messages=[("agent", text)] if text else [],
                    outbox=[text] if text else [])

    # the candidate wrote (or was erased) while we worked: leave them for the next pass
    return conversation.run(store, client, candidate_id, now, work, on_conflict=SKIP)


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
