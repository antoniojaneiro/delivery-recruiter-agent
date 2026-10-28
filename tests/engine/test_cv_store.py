"""D71: the uploaded PDF is kept with the candidate, saved in the same step as the turn, and erased for real."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from screener.store import Store

NOW = datetime(2026, 10, 25, 10, 0)
PDF = b"%PDF-1.4\n" + b"UNIQUE-CV-MARKER-Zxqvbnm " * 40 + b"\n%%EOF"


@pytest.fixture
def path(tmp_path):
    return tmp_path / "s.db"


@pytest.fixture
def store(path):
    return Store(path)


def save(store, cid="c1", cv=PDF):
    store.commit_turn(cid, NOW, {"consent": True}, {}, "IN_PROGRESS", [], [("candidate", "[CV uploaded]")], cv=cv)


def test_a_saved_cv_can_be_read_back_with_its_size_and_fingerprint(store):
    import hashlib
    save(store)
    cv = store.cv("c1")
    assert cv.data == PDF and cv.size == len(PDF) and cv.uploaded_at == NOW
    assert cv.sha256 == hashlib.sha256(PDF).hexdigest()


def test_a_candidate_without_a_cv_has_none(store):
    save(store, cv=None)
    assert store.cv("c1") is None and store.cv("nobody") is None


def test_a_turn_that_fails_saves_no_cv(store):
    from screener.store import ConflictError
    save(store)
    with pytest.raises(ConflictError):
        store.commit_turn("c1", NOW, {}, {}, "IN_PROGRESS", [], [], cv=b"%PDF-second", expected_version=99)
    assert store.cv("c1").data == PDF


def test_erasing_a_candidate_removes_the_cv_bytes_from_the_file_and_its_log(store, path):
    save(store)
    save(store, cid="c2", cv=b"%PDF-1.4 other candidate's file")
    assert b"UNIQUE-CV-MARKER" in b"".join(p.read_bytes() for p in (Path(path), Path(str(path) + "-wal")) if p.exists())
    store.erase_candidate("c1", "recruiter:Ana", NOW, "request")
    raw = b"".join(p.read_bytes() for p in (Path(path), Path(str(path) + "-wal")) if p.exists())
    assert b"UNIQUE-CV-MARKER" not in raw
    assert store.cv("c1") is None and store.cv("c2") is not None
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM cvs WHERE candidate_id = 'c1'").fetchone()[0] == 0
    db.close()
