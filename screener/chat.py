import json
import sqlite3
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from screener import turn
from screener.client import Client
from screener.llm import LLM
from screener.phrasing import Directive, Kind, phrase
from screener.store import Store

HELP = "Commands: /new, /resume <id>, /state, /inbox, /wait24h, /help, /quit"


def run(llm: LLM, store: Store, client: Client, read=input, write=print,
        clock=datetime.now, log_path: Path | None = None) -> None:
    def report(error: Exception) -> None:
        write(log_error(error, clock(), log_path))

    candidate_id = None
    try:
        candidate_id = _new(store, client, clock, write)
    except Exception as error:
        report(error)
        write(f"[no active candidate] Type /new to start one. {HELP}")
    while True:
        try:
            line = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            continue
        if line.startswith("/"):
            command, _, arg = line.partition(" ")
            if command == "/quit":
                return
            try:
                candidate_id = _command(command, arg.strip(), candidate_id, llm, store, client, clock, write)
            except Exception as error:
                report(error)
            continue
        if candidate_id is None:
            write("[no active candidate] Type /new to start one.")
            continue
        try:
            write(f"bot> {turn.handle_message(llm, store, client, candidate_id, line, clock())}")
        except Exception as error:
            report(error)
            write("bot> " + phrase(llm, client.spec, Directive(Kind.TECHNICAL_ERROR), client.spec.pack.default_language))


def log_error(error: Exception, now: datetime, log_path: Path | None) -> str:
    """Appends the error to the log (never the candidate's text) and returns the line to show the operator."""
    error_id = uuid.uuid4().hex[:6]
    if log_path is None:
        return f"[error {error_id}: not logged]"
    detail = "".join(traceback.format_exception(error))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"[{now.isoformat()}] {error_id} {type(error).__name__}\n{detail}\n")
    except OSError:
        return f"[error {error_id}: could not write {log_path}]"
    return f"[error {error_id}: see {log_path}]"


def _draw_id() -> str:
    return uuid.uuid4().hex[:12]


def _new(store, client, clock, write) -> str:
    candidate_id = _draw_id()
    while store.get(candidate_id) is not None:  # never merge two applicants into one record
        candidate_id = _draw_id()
    text = turn.start(store, client, candidate_id, clock())
    write(f"[candidate {candidate_id}]")
    write(f"bot> {text}")
    return candidate_id


def _command(command, arg, candidate_id, llm, store, client, clock, write) -> str | None:
    if command == "/new":
        return _new(store, client, clock, write)
    if command == "/resume":
        if store.get(arg) is None:
            write(f"[candidate {arg or '?'} not found]")
            return candidate_id
        write(f"[resumed {arg}]")
        return arg
    if command == "/help":
        write(HELP)
        return candidate_id
    if command == "/inbox":
        return _show_inbox(store, candidate_id, clock, write)
    if command == "/state":
        return _show_state(store, candidate_id, write)
    if command == "/wait24h":
        if candidate_id is None:
            write("[no active candidate] Type /new to start one.")
            return candidate_id
        reply = turn.wait_24h(llm, store, client, candidate_id, clock())
        write(f"bot> {reply}" if reply else "[no reply: stalled or already finished]")
        return candidate_id
    write(f"[unknown command {command}] {HELP}")
    return candidate_id


def _show_inbox(store, candidate_id, clock, write) -> str | None:
    """Messages the reminder job queued for this candidate: the terminal has no way to send them by itself."""
    pending = store.outbox_pending(candidate_id) if candidate_id else []
    if not pending:
        write("[no queued messages for this candidate]")
    for entry in pending:
        write(f"bot> {entry.text}")
        store.mark_delivered(entry.id, clock())
    return candidate_id


def _show_state(store, candidate_id, write) -> str | None:
    record = store.get(candidate_id) if candidate_id else None
    if record is None:
        write("[state] outcome: (nothing saved yet)")
        return candidate_id
    write(f"[state] outcome: {record.outcome}  reasons: {record.reasons}  flags: {record.flags}")
    write("[state] data: " + json.dumps(record.extracted, ensure_ascii=False))
    for line in (record.summary or "").splitlines():
        write(f"[state]   {line}")
    if record.booking:
        write(f"[state] booked slot {record.booking.slot_id}: {record.booking.starts_at:%Y-%m-%d %H:%M} ({record.booking.country})")
    return candidate_id


def main(client: Client, db_path: Path, log_path: Path, title: str) -> None:
    from screener import gemini
    from screener.llm import LLMError

    try:
        llm = gemini.from_env()
    except LLMError as error:
        sys.exit(str(error))
    try:
        store = Store(db_path, calendar=client.calendar)
    except (OSError, sqlite3.Error) as error:
        sys.exit(f"Cannot open the database at {db_path}: {error}")
    if "--list-models" in sys.argv:
        print("\n".join(llm.models()))
        return
    print(f"{title} (model {llm.model}). {HELP}\n")
    run(llm, store, client, log_path=log_path)
