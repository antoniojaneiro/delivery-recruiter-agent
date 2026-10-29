"""The database layout: tables, then columns added after the first release, then indexes and triggers (in that
order, because indexes may use the new columns)."""
import sqlite3

_TABLES = """
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT '{}',
    extracted TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    outcome TEXT,
    reasons TEXT NOT NULL DEFAULT '[]',
    flags TEXT NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    type TEXT NOT NULL,
    detail TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'agent',
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recruiter (
    candidate_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'new',
    assignee TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    recruiter TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    candidate_id TEXT,
    booked_at TEXT,
    cancelled_at TEXT,
    cancelled_by TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    changed_by TEXT,
    changed_at TEXT
);
CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cvs (
    candidate_id TEXT PRIMARY KEY,
    data BLOB NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    candidate_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voice_sessions (
    session_hash TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS replies (
    candidate_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    reply TEXT,
    PRIMARY KEY (candidate_id, message_id)
);
CREATE TABLE IF NOT EXISTS recruiters (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    salt TEXT NOT NULL,
    hash TEXT NOT NULL,
    params TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_failures (
    key TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS availability (
    email TEXT NOT NULL,
    weekday INTEGER NOT NULL,
    start_min INTEGER NOT NULL,
    end_min INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS availability_custom (email TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS days_off (
    email TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (email, day)
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
"""

_ONE_CALL_AT_A_TIME = ("CREATE UNIQUE INDEX IF NOT EXISTS one_call_per_recruiter_time ON slots(recruiter, starts_at) "
                       "WHERE recruiter IS NOT NULL AND cancelled_at IS NULL")

_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_candidate
    ON slots(candidate_id) WHERE candidate_id IS NOT NULL AND cancelled_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_candidates_outcome ON candidates(outcome);
CREATE INDEX IF NOT EXISTS idx_events_candidate ON events(candidate_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_candidate ON messages(candidate_id, id);
CREATE INDEX IF NOT EXISTS idx_slots_country_start ON slots(country, starts_at);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(delivered_at, candidate_id);
CREATE INDEX IF NOT EXISTS idx_notes_candidate ON notes(candidate_id, id);
CREATE INDEX IF NOT EXISTS idx_login_failures ON login_failures(key, at);
"""

# A counter that moves whenever anything the candidate list shows changes, so the dashboard can cache the list
# and read it again only when the counter has moved. Triggers keep it right whoever writes (chat, job, dashboard).
_TRIGGERS = "".join(
    f"CREATE TRIGGER IF NOT EXISTS rev_{table}_{event.lower()} AFTER {event} ON {table} BEGIN "
    "UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key = 'rev'; END;\n"
    for table in ("candidates", "recruiter", "slots") for event in ("INSERT", "UPDATE", "DELETE"))

# Columns added after the first release; databases created earlier are upgraded in place.
_ADDED_COLUMNS = {
    "candidates": {"reasons": "TEXT NOT NULL DEFAULT '[]'", "flags": "TEXT NOT NULL DEFAULT '[]'",
                   "outcome": "TEXT", "version": "INTEGER NOT NULL DEFAULT 0"},
    "events": {"actor": "TEXT NOT NULL DEFAULT 'agent'"},
    "slots": {"recruiter": "TEXT", "candidate_id": "TEXT", "booked_at": "TEXT", "cancelled_at": "TEXT",
              "cancelled_by": "TEXT"},
}


def prepare(db: sqlite3.Connection) -> None:
    """Creates or upgrades the layout in place. Safe to run again, and by several processes at once."""
    db.execute("PRAGMA journal_mode=WAL")  # readers (the dashboard) do not block the chat's writes
    db.executescript(_TABLES)
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                try:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                except sqlite3.OperationalError:  # another process added it first
                    pass
    db.executescript(_INDEXES)
    try:  # a recruiter takes one call at a time; a database that already breaks that keeps working without the guard
        db.execute(_ONE_CALL_AT_A_TIME)
    except sqlite3.IntegrityError:
        pass
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('rev', '0')")
    db.executescript(_TRIGGERS)
