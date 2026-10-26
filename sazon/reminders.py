"""Grupo Sazón's 24-hour reminder job (D35, D58, D63): `python -m sazon.reminders`. The job itself is the engine's."""
from screener import reminders
from sazon import config
from sazon.client import SAZON_CLIENT


def main(argv: list[str] | None = None) -> None:
    reminders.main(SAZON_CLIENT, config.db_path(), "python -m sazon.reminders", argv)


if __name__ == "__main__":
    main()
