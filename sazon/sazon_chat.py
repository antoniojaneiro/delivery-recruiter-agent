"""Grupo Sazón's terminal chat (D1, D63): `python -m sazon.chat`. The loop itself is the engine's."""
from sazon import chat, config
from sazon.sazon_client import SAZON_CLIENT


def main() -> None:
    chat.main(SAZON_CLIENT, config.db_path(), config.LOG_PATH, "Grupo Sazón screening chat")


if __name__ == "__main__":
    main()
