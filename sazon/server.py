"""Grupo Sazón's HTTP service (D75): `python -m sazon.server`. The service itself is the engine's."""
import os

from dotenv import load_dotenv

from sazon import config
from sazon.client import SAZON_CLIENT
from screener import gemini
from screener.llm import LLM
from screener.service import create_app
from screener.store import Store


def build_app(llm: LLM):
    """The key for channel adapters must be set: a service anyone may start candidates on is not for a network."""
    api_key = os.environ.get("SAZON_API_KEY")
    if not api_key:
        raise RuntimeError("SAZON_API_KEY is not set. Add a long random value to .env.")
    return create_app(SAZON_CLIENT, Store(config.db_path(), calendar=SAZON_CLIENT.calendar), llm, api_key=api_key,
                      log_path=config.LOG_PATH)


def main() -> None:
    import uvicorn

    load_dotenv()
    uvicorn.run(build_app(gemini.from_env(load_dotenv_file=False)),
                host=os.environ.get("SAZON_HOST", "127.0.0.1"), port=int(os.environ.get("SAZON_PORT", "8000")))


if __name__ == "__main__":
    main()
