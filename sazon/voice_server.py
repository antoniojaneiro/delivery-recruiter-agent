"""Grupo Sazón's voice endpoint (D93): `python -m sazon.voice_server`, started by `python -m sazon.voice_launch`. The endpoint itself
is the engine's; this plugs the client in. It only starts with the shared secret ElevenLabs sends back to it."""
import os

from dotenv import load_dotenv

from sazon import config
from sazon.client import SAZON_CLIENT
from screener import gemini
from screener.llm import LLM
from screener.store import Store
from screener.voice_service import create_voice_app


def build_app(llm: LLM):
    secret = os.environ.get("VOICE_LLM_SECRET")
    if not secret:
        raise RuntimeError("VOICE_LLM_SECRET is not set: start this with python -m sazon.voice_launch.")
    return create_voice_app(SAZON_CLIENT, Store(config.db_path(), calendar=SAZON_CLIENT.calendar), llm, secret=secret,
                            log_path=config.LOG_PATH)


def main() -> None:
    import uvicorn

    load_dotenv()
    uvicorn.run(build_app(gemini.from_env(load_dotenv_file=False)), host="127.0.0.1", port=config.voice_port())


if __name__ == "__main__":
    main()
