"""One sign-in for the dashboard (D80): the hiring manager (email and password from the environment, handed in by the
caller, never stored) or a recruiter the manager created. A wrong password counts toward the same lockout either way.
The manager also takes calls (D89): they are a recruiter in the database too, with a password nobody knows, so they have
hours and bookings like anyone, and they sign in only with the environment's password."""
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime

from screener.recruiters import TooManyAttempts, normal_email, spend_the_same_time

MANAGER_NAME = "Hiring manager"


@dataclass(frozen=True)
class Identity:
    email: str  # the one key for a person: audit lines, availability and calls all use it
    name: str
    role: str  # "manager" or "recruiter"
    country: str | None  # the country whose calls they take


def ensure_manager_takes_calls(store, manager: tuple[str, str] | None, country: str, now: datetime) -> None:
    """Makes the hiring manager a recruiter in `country`, with the client's default week, if they are not one yet. The
    password stored for that row is thrown away: signing in as the manager is checked against the environment only."""
    if manager is None or not manager[1]:
        return
    email = normal_email(manager[0])
    if store.get_recruiter(email) is None:
        store.add_recruiter(email, MANAGER_NAME, country, secrets.token_urlsafe(24), "system", now)


def sign_in(store, email: str, password: str, manager: tuple[str, str] | None, now: datetime) -> Identity | None:
    """Who signed in, or None for a wrong email or password. Raises TooManyAttempts after five wrong passwords."""
    key = normal_email(email)
    if manager is not None and manager[1] and key == normal_email(manager[0]):
        if store.locked(key, now):
            raise TooManyAttempts(key)
        ok = hmac.compare_digest((password or "").encode("utf-8"), manager[1].encode("utf-8"))
        store.note_login(key, ok, now)
        taking_calls = store.get_recruiter(key)
        return Identity(key, MANAGER_NAME, "manager", taking_calls.country if taking_calls else None) if ok else None
    if manager is None or not key:
        spend_the_same_time(password)  # the same work for every wrong answer
    found = store.verify_recruiter(key, password, now) if key else None
    return Identity(found.email, found.name, "recruiter", found.country) if found else None
