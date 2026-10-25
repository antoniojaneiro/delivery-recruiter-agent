"""Erases rejected, withdrawn and off-topic candidates after the retention period (D53).

    python -m sazon.retention                 # dry run: lists who would be erased
    python -m sazon.retention --apply         # erases them

The six months (183 days) are a default to confirm with the client's legal team (P4)."""
import argparse
from datetime import datetime, timedelta

from sazon import config
from sazon.model import RecruiterStatus
from sazon.store import Record, Store

RETENTION_DAYS = 183
ERASABLE_OUTCOMES = ("DISQUALIFIED", "WITHDRAWN", "ENDED_OFF_TOPIC")
# A recruiter who overruled the agent, or is working with the candidate, keeps the record: the agent's outcome
# alone must not erase them (D42, D52).
KEPT_STATUSES = (RecruiterStatus.HIRED, RecruiterStatus.INTERVIEW_SCHEDULED, RecruiterStatus.CONTACTED)


def _naive(moment: datetime) -> datetime:
    return moment.replace(tzinfo=None)


def due(store: Store, now: datetime, days: int = RETENTION_DAYS) -> list[Record]:
    cutoff = _naive(now) - timedelta(days=days)
    return [r for r in store.list_candidates()
            if r.outcome in ERASABLE_OUTCOMES and r.status not in KEPT_STATUSES and _naive(r.updated_at) < cutoff]


def apply(store: Store, now: datetime, days: int = RETENTION_DAYS) -> list[str]:
    erased = []
    for record in due(store, now, days):
        if store.erase_candidate(record.candidate_id, "retention", now, "retention"):
            erased.append(record.candidate_id)
    return erased


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sazon.retention", description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="erase them (the default is a dry run)")
    parser.add_argument("--days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--now", help="the moment to count from (ISO format; for tests)")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    store = Store(config.db_path())
    if args.apply:
        erased = apply(store, now, args.days)
        print(f"Erased {len(erased)} candidate(s) older than {args.days} days.")
        return
    waiting = due(store, now, args.days)
    for record in waiting:
        print(f"{record.candidate_id}  {record.outcome}  last activity {record.updated_at:%Y-%m-%d}")
    print(f"Dry run: {len(waiting)} candidate(s) older than {args.days} days would be erased. Use --apply to erase them.")


if __name__ == "__main__":
    main()
