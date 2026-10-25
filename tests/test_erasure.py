"""D53: erasing a candidate really removes the data, and retention erases rejected candidates after six months."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sazon import retention
from sazon.model import RecruiterStatus
from sazon.store import Store

NOW = datetime(2026, 10, 25, 10, 0)
MARK = "Zxqvbnm Unico"
PHONE = "600987654"


@pytest.fixture
def path(tmp_path):
    return tmp_path / "sazon.db"


@pytest.fixture
def store(path):
    return Store(path)


def fill(store, cid="c1", name=MARK, outcome="QUALIFIED", when=NOW):
    store.commit_turn(cid, when, {"consent": True, "values": {"name": name}}, {"name": name}, outcome,
                      [("consent_given", "")], [("candidate", f"me llamo {name}, tel {PHONE}"), ("agent", "ok")],
                      summary=f"{name} · Madrid · Cualificado")
    store.set_status(cid, RecruiterStatus.CONTACTED, "Ana", NOW)
    store.add_note(cid, f"llamó {name}", "Ana", NOW)


def rows(path, table, cid="c1"):
    db = sqlite3.connect(path)
    try:
        return db.execute(f"SELECT COUNT(*) FROM {table} WHERE candidate_id = ?", (cid,)).fetchone()[0]
    finally:
        db.close()


def raw_bytes(path):
    parts = [Path(path), Path(str(path) + "-wal")]
    return b"".join(p.read_bytes() for p in parts if p.exists())


def test_erasing_removes_the_candidate_from_every_table(store, path):
    fill(store)
    slot = store.add_slot("ES", datetime(2027, 6, 15, 10, 0), "Ana", "Ana", NOW.astimezone())
    store.book_slot(slot, "c1", NOW.astimezone())
    assert store.erase_candidate("c1", "recruiter:Ana", NOW, "request") is True
    for table in ("candidates", "events", "messages", "notes", "recruiter"):
        assert rows(path, table) == 0, table
    assert store.get("c1") is None and store.booking_of("c1") is None
    assert [s.candidate_id for s in store.slots(NOW.astimezone())] == [None]  # the slot is free again


def test_the_data_is_physically_gone_from_the_database_and_its_log(store, path):
    fill(store)
    assert MARK.encode() in raw_bytes(path)  # so the check below proves something
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    data = raw_bytes(path)
    assert MARK.encode() not in data and PHONE.encode() not in data
    assert "Cualificado".encode() not in data


def test_other_candidates_are_untouched(store):
    fill(store, "c1")
    fill(store, "c2", name="Otra Persona")
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    assert store.get("c2").extracted == {"name": "Otra Persona"} and len(store.notes("c2")) == 1


def test_the_admin_log_keeps_an_anonymous_line_with_who_and_why(store):
    fill(store)
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    [entry] = [e for e in store.admin_log() if e.action == "candidate_erased"]
    assert entry.actor == "recruiter:Ana" and "reason=request" in entry.detail
    assert "c1" not in entry.detail and MARK not in entry.detail and "id_sha256=" in entry.detail


def test_erasing_an_unknown_candidate_does_nothing_and_says_so(store):
    assert store.erase_candidate("ghost", "recruiter:Ana", NOW, "request") is False
    assert [e for e in store.admin_log() if e.action == "candidate_erased"] == []


# --- retention ---------------------------------------------------------------------------------------------

OLD = NOW - timedelta(days=200)
RECENT = NOW - timedelta(days=30)


def populate(store):
    fill(store, "old-rejected", outcome="DISQUALIFIED", when=OLD)
    fill(store, "old-withdrawn", outcome="WITHDRAWN", when=OLD)
    fill(store, "old-offtopic", outcome="ENDED_OFF_TOPIC", when=OLD)
    fill(store, "old-qualified", outcome="QUALIFIED", when=OLD)
    fill(store, "old-progress", outcome="IN_PROGRESS", when=OLD)
    fill(store, "old-blocked", outcome="BLOCKED", when=OLD)
    fill(store, "recent-rejected", outcome="DISQUALIFIED", when=RECENT)


def test_only_old_rejected_withdrawn_and_off_topic_candidates_are_due(store):
    populate(store)
    due = sorted(r.candidate_id for r in retention.due(store, NOW))
    assert due == ["old-offtopic", "old-rejected", "old-withdrawn"]


def test_the_limit_is_six_months_by_default_and_can_be_changed(store):
    populate(store)
    assert "recent-rejected" not in [r.candidate_id for r in retention.due(store, NOW)]
    assert "recent-rejected" in [r.candidate_id for r in retention.due(store, NOW, days=10)]


def test_applying_erases_the_due_candidates_as_the_retention_job(store):
    populate(store)
    erased = retention.apply(store, NOW)
    assert sorted(erased) == ["old-offtopic", "old-rejected", "old-withdrawn"]
    assert store.get("old-rejected") is None and store.get("old-qualified") is not None
    log = [e for e in store.admin_log() if e.action == "candidate_erased"]
    assert len(log) == 3 and all(e.actor == "retention" and "reason=retention" in e.detail for e in log)


def test_a_dry_run_changes_nothing_and_lists_who_would_go(store, path, monkeypatch, capsys):
    populate(store)
    monkeypatch.setenv("SAZON_DB", str(path))
    retention.main(["--now", NOW.isoformat()])
    out = capsys.readouterr().out
    assert "old-rejected" in out and "dry run" in out.lower() and "--apply" in out
    assert store.get("old-rejected") is not None


def test_the_command_with_apply_erases(store, path, monkeypatch, capsys):
    populate(store)
    monkeypatch.setenv("SAZON_DB", str(path))
    retention.main(["--apply", "--now", NOW.isoformat()])
    assert store.get("old-rejected") is None and "3" in capsys.readouterr().out
