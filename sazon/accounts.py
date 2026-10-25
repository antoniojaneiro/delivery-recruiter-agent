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
from pathlib import Path

MIN_PASSWORD_LENGTH = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_DUMMY_SALT = bytes(16)


def accounts_path() -> Path:
    return Path(os.environ.get("SAZON_ACCOUNTS") or Path("data") / "recruiters.json")


def _key(name: str) -> str:
    return " ".join((name or "").split()).casefold()


def _hash(password: str, salt: bytes, params: dict) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params["n"], r=params["r"], p=params["p"],
                          dklen=params["dklen"])


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
    data = _read(path)
    if _key(clean) in data and not replace:
        raise ValueError(f"there is already an account for {clean}")
    salt = secrets.token_bytes(16)
    data[_key(clean)] = {"name": clean, "algorithm": "scrypt", "params": dict(SCRYPT), "salt": salt.hex(),
                         "hash": _hash(password, salt, SCRYPT).hex()}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def remove_account(path: Path, name: str) -> bool:
    data = _read(path)
    if data.pop(_key(name), None) is None:
        return False
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def verify(path: Path, name: str, password: str) -> str | None:
    """The name as registered when the password is right, else None. It does the same work either way, so the
    time taken does not reveal which names have an account."""
    entry = _read(path).get(_key(name))
    if entry is None:
        _hash(password or "", _DUMMY_SALT, SCRYPT)
        return None
    expected = bytes.fromhex(entry["hash"])
    given = _hash(password or "", bytes.fromhex(entry["salt"]), entry["params"])
    return entry["name"] if hmac.compare_digest(expected, given) else None


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
        print("Removed." if remove_account(path, args.name) else "No such account.")
        return
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat the password: "):
        sys.exit("The passwords do not match.")
    try:
        add_account(path, args.name, password)
    except ValueError as error:
        sys.exit(str(error))
    print(f"Account created for {args.name}.")


if __name__ == "__main__":
    main()
