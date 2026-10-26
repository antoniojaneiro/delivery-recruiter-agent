"""Where Grupo Sazón keeps its recruiter accounts (D57, D63): the engine's `accounts` module does the work."""
import os
from pathlib import Path

from sazon import accounts
from sazon.config import PROJECT_ROOT


def accounts_path() -> Path:
    return Path(os.environ.get("SAZON_ACCOUNTS") or PROJECT_ROOT / "data" / "recruiters.json")


def main(argv: list[str] | None = None) -> None:
    accounts.cli(accounts_path(), "python -m sazon.accounts", argv)


if __name__ == "__main__":
    main()
