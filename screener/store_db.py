"""The SQLite file and its connections, shared by the parts of the store (D3, D44, D88). Each part (the candidates in
`Store`, the call times, the service's records) asks this for a connection and for the client's calendar, and nothing else
about the others."""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from screener.store_schema import prepare
from screener.store_types import InputError, stamp

BUSY_TIMEOUT_SECONDS = 10


class Database:
    def __init__(self, path: Path | str, calendar=None):
        self.path = str(path)
        self.calendar = calendar  # None: this client does not book calls
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(40):  # several processes may open a new or old file at the same moment
            try:
                with self.connect() as db:
                    prepare(db)
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error) or attempt == 39:
                    raise
                time.sleep(0.25)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_SECONDS)
        try:
            with db:
                yield db
        finally:
            db.close()

    def require_calendar(self):
        if self.calendar is None:
            raise InputError("no_calendar", "this client does not book calls")
        return self.calendar

    @staticmethod
    def log(db, actor: str, action: str, detail: str, now: datetime) -> int:
        """One line of the log of what people did (D56), written inside the caller's transaction."""
        return db.execute("INSERT INTO admin_log (actor, action, detail, at) VALUES (?, ?, ?, ?)",
                          (actor, action, detail, stamp(now))).lastrowid


class Part:
    """What every part of the store holds: the database. A part reaches the others only through the store."""

    def __init__(self, db: Database):
        self._db = db

    @property
    def calendar(self):
        return self._db.calendar

    def _connect(self):
        return self._db.connect()

    def _calendar(self):
        return self._db.require_calendar()

    _log = staticmethod(Database.log)
