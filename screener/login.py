"""One sign-in for the dashboard (D80): the hiring manager (email and password from the environment, handed in by the
caller, never stored) or a recruiter the manager created. A wrong password counts toward the same lockout either way."""
import hmac
from dataclasses import dataclass
from datetime import datetime

from screener.recruiters import TooManyAttempts, normal_email, spend_the_same_time

MANAGER_NAME = "Hiring manager"


@dataclass(frozen=True)
class Identity:
    email: str  # the one key for a person: audit lines, availability and calls all use it
    name: str
    role: str  # "manager" or "recruiter"
    country: str | None  # a recruiter's country; the manager has none (the manager is not a recruiter)


def sign_in(store, email: str, password: str, manager: tuple[str, str] | None, now: datetime) -> Identity | None:
    """Who signed in, or None for a wrong email or password. Raises TooManyAttempts after five wrong passwords."""
    key = normal_email(email)
    if manager is not None and manager[1] and key == normal_email(manager[0]):
        if store.locked(key, now):
            raise TooManyAttempts(key)
        ok = hmac.compare_digest((password or "").encode("utf-8"), manager[1].encode("utf-8"))
        store.note_login(key, ok, now)
        return Identity(key, MANAGER_NAME, "manager", None) if ok else None
    if manager is None or not key:
        spend_the_same_time(password)  # the same work for every wrong answer
    found = store.verify_recruiter(key, password, now) if key else None
    return Identity(found.email, found.name, "recruiter", found.country) if found else None
