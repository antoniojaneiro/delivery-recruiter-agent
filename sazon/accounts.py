"""Recruiter accounts for the dashboard (D57): one per recruiter, passwords only as salted scrypt hashes.

    python -m sazon.accounts add Ana       # asks for the password twice
    python -m sazon.accounts list
    python -m sazon.accounts remove Ana

The file (data/recruiters.json, or the path in SAZON_ACCOUNTS) is never committed. This is a prototype measure; a
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

from sazon.config import PROJECT_ROOT

MIN_PASSWORD_LENGTH = 8
SCRYPT = {"n": 2 ** 16, "r": 8, "p": 1, "dklen": 32}
MAX_FAILURES = 5
LOCK_SECONDS = 600
_failures: dict[str, list[float]] = {}


class DamagedAccounts(Exception):
    """The accounts file exists but cannot be read, so it is left alone rather than overwritten."""


class TooManyAttempts(Exception):
    """Too many wrong passwords for this name; try again later."""


def reset_throttle() -> None:
    _failures.clear()
_DUMMY_SALT = bytes(16)


def accounts_path() -> Path:
    return Path(os.environ.get("SAZON_ACCOUNTS") or PROJECT_ROOT / "data" / "recruiters.json")


def _key(name: str) -> str:
    return " ".join((name or "").split()).casefold()


def _hash(password: str, salt: bytes, params: dict) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params["n"], r=params["r"], p=params["p"],
                          dklen=params["dklen"], maxmem=2 ** 28)


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


def add_account(path: Path, name: str, password: str, replace: bool = False) -> None:
    clean = " ".join((name or "").split())
    if not clean:
        raise ValueError("a name is required")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the password needs at least {MIN_PASSWORD_LENGTH} characters")
    data = _read_for_update(path)
    if _key(clean) in data and not replace:
        raise ValueError(f"there is already an account for {clean}")
    salt = secrets.token_bytes(16)
    data[_key(clean)] = {"name": clean, "algorithm": "scrypt", "params": dict(SCRYPT), "salt": salt.hex(),
                         "hash": _hash(password, salt, SCRYPT).hex()}
    _write(path, data)


def remove_account(path: Path, name: str) -> bool:
    data = _read_for_update(path)
    if data.pop(_key(name), None) is None:
        return False
    _write(path, data)
    return True


def verify(path: Path, name: str, password: str, now: float | None = None) -> str | None:
    """The name as registered when the password is right, else None. It does the same work either way, so the
    time taken does not reveal which names have an account. After MAX_FAILURES wrong passwords the name is locked
    for LOCK_SECONDS (in this process's memory) and TooManyAttempts is raised."""
    now = time.monotonic() if now is None else now
    key = _key(name)
    recent = [t for t in _failures.get(key, []) if now - t < LOCK_SECONDS]
    if len(recent) >= MAX_FAILURES:
        _failures[key] = recent
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
        _failures[key] = recent + [now]
    else:
        _failures.pop(key, None)
    return verified


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sazon.accounts", description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["add", "list", "remove"])
    parser.add_argument("name", nargs="?")
    args = parser.parse_args(argv)
    path = accounts_path()
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


if __name__ == "__main__":
    main()
