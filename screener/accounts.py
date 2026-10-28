"""Recruiter accounts for the dashboard (D57): one per recruiter, passwords only as salted scrypt hashes.

    python -m <client>.accounts add Ana       # asks for the password twice
    python -m <client>.accounts list
    python -m <client>.accounts remove Ana

The client's entry point says where the file is. The file is never committed. This is a prototype measure; a
real deployment should use the company's single sign-on. A missing or damaged file means nobody can sign in."""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

MIN_PASSWORD_LENGTH = 8
SCRYPT = {"n": 2 ** 16, "r": 8, "p": 1, "dklen": 32}
MAX_FAILURES = 5
LOCK_SECONDS = 600


class DamagedAccounts(Exception):
    """The accounts file exists but cannot be read, so it is left alone rather than overwritten."""


class TooManyAttempts(Exception):
    """Too many wrong passwords for this name; try again later."""


_DUMMY_SALT = bytes(16)


def _key(name: str) -> str:
    return " ".join((name or "").split()).casefold()


def _hash(password: str, salt: bytes, params: dict) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params["n"], r=params["r"], p=params["p"],
                          dklen=params["dklen"], maxmem=2 ** 28)


def failures_path(path: Path) -> Path:
    return Path(str(path) + ".failures")


def _read_failures(path: Path) -> dict:
    try:
        data = json.loads(failures_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if _valid(v)}


def _valid(entry) -> bool:
    try:
        return (isinstance(entry, dict) and isinstance(entry["name"], str) and bool(bytes.fromhex(entry["salt"]))
                and bool(bytes.fromhex(entry["hash"])) and all(isinstance(entry["params"][k], int) for k in SCRYPT))
    except (KeyError, TypeError, ValueError):
        return False


def _read_for_update(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise DamagedAccounts(str(path)) from None
    if not isinstance(data, dict):
        raise DamagedAccounts(str(path))
    return data


def _write(path: Path, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=Path(path).parent, suffix=".tmp", delete=False) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
    os.replace(tmp.name, path)


def has_accounts(path: Path) -> bool:
    return bool(_read(path))


def list_names(path: Path) -> list[str]:
    return sorted(entry["name"] for entry in _read(path).values())


class AccountError(ValueError):
    """An account that cannot be created. `code` says why, so a screen need not read the English message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def create_first(path: Path, name: str, password: str) -> str:
    """The very first account, for an install with none. Refused once any account exists, so this can never be used
    to add a second one without signing in."""
    return add_account(path, name, password, only_first=True)


def add_account(path: Path, name: str, password: str, replace: bool = False, only_first: bool = False) -> str:
    """Creates the account and returns the name as stored."""
    clean = " ".join((name or "").split())
    if not clean:
        raise AccountError("name_required", "a name is required")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError("password_short", f"the password needs at least {MIN_PASSWORD_LENGTH} characters")
    data = _read_for_update(path)
    if only_first and data:
        raise AccountError("not_first", "accounts already exist: sign in to add another")
    if _key(clean) in data and not replace:
        raise AccountError("exists", f"there is already an account for {clean}")
    salt = secrets.token_bytes(16)
    data[_key(clean)] = {"name": clean, "algorithm": "scrypt", "params": dict(SCRYPT), "salt": salt.hex(),
                         "hash": _hash(password, salt, SCRYPT).hex()}
    _write(path, data)
    return clean


def remove_account(path: Path, name: str) -> bool:
    data = _read_for_update(path)
    if data.pop(_key(name), None) is None:
        return False
    _write(path, data)
    return True


def verify(path: Path, name: str, password: str, now: float | None = None) -> str | None:
    """The name as registered when the password is right, else None. It does the same work either way, so the
    time taken does not reveal which names have an account. After MAX_FAILURES wrong passwords the name is locked
    for LOCK_SECONDS and TooManyAttempts is raised. The failures are kept in a file beside the accounts file, so a
    restart or a second process does not clear a lockout."""
    now = time.time() if now is None else now
    key = _key(name)
    failures = _read_failures(path)
    recent = [t for t in failures.get(key, []) if isinstance(t, (int, float)) and now - t < LOCK_SECONDS]
    if len(recent) >= MAX_FAILURES:
        raise TooManyAttempts(key)
    entry = _read(path).get(key)
    if entry is None:
        _hash(password or "", _DUMMY_SALT, SCRYPT)
        verified = None
    else:
        expected = bytes.fromhex(entry["hash"])
        given = _hash(password or "", bytes.fromhex(entry["salt"]), entry["params"])
        verified = entry["name"] if hmac.compare_digest(expected, given) else None
    if verified is None:
        failures[key] = recent + [now]
    else:
        failures.pop(key, None)
    failures = {k: v for k, v in failures.items() if v}
    try:
        _write(failures_path(path), failures)
    except OSError:
        pass  # the check still counts for this call; a read-only folder must not stop a sign-in
    return verified


def cli(path: Path, prog: str, argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["add", "list", "remove"])
    parser.add_argument("name", nargs="?")
    args = parser.parse_args(argv)
    if args.action == "list":
        print("\n".join(list_names(path)) or "(no accounts)")
        return
    if not args.name:
        sys.exit("A name is required.")
    if args.action == "remove":
        try:
            print("Removed." if remove_account(path, args.name) else "No such account.")
        except DamagedAccounts:
            sys.exit(f"{path} is damaged; fix or delete it by hand.")
        return
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat the password: "):
        sys.exit("The passwords do not match.")
    try:
        add_account(path, args.name, password)
    except (ValueError, DamagedAccounts) as error:
        sys.exit(str(error))
    print(f"Account created for {args.name}.")
