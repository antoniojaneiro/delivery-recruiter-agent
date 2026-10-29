"""D75: what the service keeps in the store: each candidate's token hash and the reply to each message id (D88: a part of
the store with its own tables)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from screener.store_db import Part
from screener.store_types import Claim, stamp

CLAIM_STALE_AFTER = timedelta(minutes=5)  # longer than the worst turn (model calls of 20 s with retries); then a dead process's claim is taken over


def _judge(row, now: datetime) -> Claim | None:
    """`done` or `busy` for an id already claimed; None when the id is free to claim (new, or the claim went stale)."""
    if row is None:
        return None
    if row[1] is not None:
        return Claim("done", row[1])
    return Claim("busy") if now - datetime.fromisoformat(row[0]) <= CLAIM_STALE_AFTER else None


VOICE_SESSION_MINUTES = 30  # a spoken conversation is short; after this the id opens nothing


class ServiceState(Part):
    def new_voice_session(self, candidate_id: str, now: datetime) -> str:
        """A secret id for one spoken conversation of this candidate (D93). Only its hash is kept; ElevenLabs sends it back with
        every turn, and it opens nothing else and nothing after it expires."""
        session = secrets.token_urlsafe(24)
        with self._connect() as db:
            db.execute("INSERT INTO voice_sessions (session_hash, candidate_id, expires_at) VALUES (?, ?, ?)",
                       (hashlib.sha256(session.encode()).hexdigest(), candidate_id,
                        stamp(now + timedelta(minutes=VOICE_SESSION_MINUTES))))
        return session

    def voice_session_candidate(self, session: str, now: datetime) -> str | None:
        """The candidate a live voice session belongs to, or None (unknown, expired or erased)."""
        with self._connect() as db:
            row = db.execute("SELECT candidate_id, expires_at FROM voice_sessions WHERE session_hash = ?",
                             (hashlib.sha256((session or "").encode()).hexdigest(),)).fetchone()
        return row[0] if row and row[1] > stamp(now) else None

    def set_token(self, candidate_id: str, token_hash: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO tokens (candidate_id, token_hash) VALUES (?, ?)",
                       (candidate_id, token_hash))

    def token_matches(self, candidate_id: str, token_hash: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT token_hash FROM tokens WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return row is not None and hmac.compare_digest(row[0], token_hash)

    def claim_message(self, candidate_id: str, message_id: str, now: datetime) -> Claim:
        """Exactly one caller gets `new` for a message id; a resend gets the stored reply once it is finished. A
        resend is answered by a plain read: the write lock is taken only to claim."""
        seen = self._claim_state(candidate_id, message_id, now)
        if seen is not None:
            return seen
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT claimed_at, reply FROM replies WHERE candidate_id = ? AND message_id = ?",
                             (candidate_id, message_id)).fetchone()
            seen = _judge(row, now)
            if seen is not None:
                return seen
            db.execute("INSERT OR REPLACE INTO replies (candidate_id, message_id, claimed_at) VALUES (?, ?, ?)",
                       (candidate_id, message_id, stamp(now)))
        return Claim("new")

    def _claim_state(self, candidate_id: str, message_id: str, now: datetime) -> Claim | None:
        with self._connect() as db:
            row = db.execute("SELECT claimed_at, reply FROM replies WHERE candidate_id = ? AND message_id = ?",
                             (candidate_id, message_id)).fetchone()
        return _judge(row, now)

    def finish_message(self, candidate_id: str, message_id: str, reply: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE replies SET reply = ? WHERE candidate_id = ? AND message_id = ?",
                       (reply, candidate_id, message_id))

    def release_message(self, candidate_id: str, message_id: str) -> None:
        """The work failed: the same id may be tried again."""
        with self._connect() as db:
            db.execute("DELETE FROM replies WHERE candidate_id = ? AND message_id = ? AND reply IS NULL",
                       (candidate_id, message_id))

    def candidate_message_counts(self, candidate_id: str, since: datetime) -> tuple[int, int]:
        """(the candidate's messages since `since`, all of them): what the rate limit reads."""
        with self._connect() as db:
            recent, total = db.execute(
                "SELECT COALESCE(SUM(at >= ?), 0), COUNT(*) FROM messages WHERE candidate_id = ? AND role = 'candidate'",
                (stamp(since), candidate_id)).fetchone()
        return recent, total
