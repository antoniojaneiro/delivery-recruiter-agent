"""Recruiters and how they sign in (D80, replacing D57's accounts file and D74's open sign-up). A recruiter is an email, a
name, a country and a salted scrypt hash, kept in the database so a booking can check them in one atomic step. Only the
hiring manager, whose email and password come from the environment, creates and deletes recruiters. A prototype measure:
a real deployment should use the company's single sign-on."""
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime

MIN_PASSWORD_LENGTH = 8
SCRYPT = {"n": 2 ** 16, "r": 8, "p": 1, "dklen": 32}  # tests lower `n`; a stored hash keeps the parameters it was made with
MAX_FAILURES = 5
LOCK_SECONDS = 600
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_SALT = bytes(16)


class TooManyAttempts(Exception):
    """Too many wrong passwords for this email; try again later."""


@dataclass(frozen=True)
class Recruiter:
    email: str
    name: str
    country: str
    created_at: datetime


def normal_email(email: str) -> str:
    return (email or "").strip().casefold()


def is_email(email: str) -> bool:
    return bool(_EMAIL.match(email))


def hash_password(password: str, salt: bytes | None = None, params: dict | None = None) -> tuple[bytes, bytes, dict]:
    """(salt, hash, parameters) for a password."""
    salt = secrets.token_bytes(16) if salt is None else salt
    params = dict(SCRYPT) if params is None else params
    digest = hashlib.scrypt((password or "").encode("utf-8"), salt=salt, n=params["n"], r=params["r"], p=params["p"],
                            dklen=params["dklen"], maxmem=2 ** 28)
    return salt, digest, params


def password_matches(password: str, salt: bytes, expected: bytes, params: dict) -> bool:
    return hmac.compare_digest(expected, hash_password(password, salt, params)[1])


def spend_the_same_time(password: str) -> None:
    """For an email nobody has: the same work as a real check, so the time taken does not reveal which emails exist."""
    hash_password(password or "", _DUMMY_SALT)
