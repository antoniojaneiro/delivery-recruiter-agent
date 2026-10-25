"""The 24-hour reminder job (D35, D38, D58). Run it every few minutes:

    python -m sazon.reminders                  # one pass
    python -m sazon.reminders --every 600      # keep running, one pass every 10 minutes

After 24 hours of silence a candidate gets one reminder; after 24 more hours without a reply they are marked
STALLED. A qualified candidate who ignores the slot offer gets one reminder with the free slots, then the 48-hour
promise. The terminal chat has nowhere to deliver a message by itself, so the texts are queued in an outbox
(`/inbox` in the chat shows them) for the real channel to send.

It only compares the chat's own timestamps (never the dashboard's), takes `now` as a parameter, does nothing while
applications are closed, and skips a candidate whose record changed while it worked."""
import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sazon import config, session, slot_flow
from sazon.model import Outcome
from sazon.phrasing import phrase
from sazon.store import ConflictError, Store

REMIND_AFTER = timedelta(hours=24)
WATCHED = (Outcome.IN_PROGRESS, Outcome.BLOCKED, Outcome.QUALIFIED)


@dataclass(frozen=True)
class Action:
    candidate_id: str
    kind: str  # "reminder", "stalled", "gave_up_offer" or "error"


def _naive(moment: datetime) -> datetime:
    return moment.replace(tzinfo=None)


def run_once(store: Store, areas: dict[str, list[str]], now: datetime) -> list[Action]:
    if not store.accepting_applications():
        return []
    now = _naive(now)
    activity = store.last_activity()
    actions = []
    for record in store.list_candidates():
        last = activity.get(record.candidate_id)
        if record.outcome not in WATCHED or last is None or now - _naive(last) < REMIND_AFTER:
            continue
        try:
            action = _remind(store, areas, record.candidate_id, now)
        except Exception:  # noqa: BLE001  one damaged record must not stop the pass for everyone else
            action = Action(record.candidate_id, "error")
        if action:
            actions.append(action)
    return actions


def _remind(store: Store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> Action | None:
    last = store.last_activity_of(candidate_id)  # fresh: they may have written since the pass started
    if last is None or now - _naive(last) < REMIND_AFTER:
        return None
    screening = session.load(store, candidate_id, areas)
    if screening.needs_consent:
        return None  # they have not agreed to anything yet, so they are not contacted again
    if screening.awaiting_slot_choice:
        kind, directive = slot_flow.on_idle(store, screening, now)
    elif screening.is_open:
        directive = screening.on_silence()
        kind = "reminder" if directive else "stalled"
    else:
        return None
    text = phrase(None, directive, screening.language) if directive else None  # fixed texts: no model needed
    try:
        session.commit(store, candidate_id, screening, now,
                       messages=[("agent", text)] if text else [], outbox=[text] if text else [])
    except ConflictError:
        return None  # the candidate wrote (or was erased) while we worked: leave them for the next pass
    return Action(candidate_id, kind)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sazon.reminders", description=__doc__.split("\n\n")[0])
    parser.add_argument("--every", type=int, help="keep running, one pass every N seconds")
    parser.add_argument("--now", help="the moment to act at (ISO format; for tests)")
    args = parser.parse_args(argv)
    store = Store(config.db_path())
    while True:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now()
        for action in run_once(store, config.AREAS, now):
            print(f"{now:%Y-%m-%d %H:%M}  {action.candidate_id}  {action.kind}")
        if not args.every:
            return
        time.sleep(args.every)


if __name__ == "__main__":
    main()
