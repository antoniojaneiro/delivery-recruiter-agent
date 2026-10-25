import sys
import uuid
from datetime import datetime

from sazon import config, turn
from sazon.llm import LLM
from sazon.phrasing import Directive, Kind, phrase
from sazon.store import Store

HELP = "Commands: /new, /resume <id>, /wait24h, /quit"


def run(llm: LLM, store: Store, areas: dict[str, list[str]], read=input, write=print,
        clock=datetime.now) -> None:
    candidate_id = _new(store, areas, clock, write)
    while True:
        try:
            line = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            continue
        if line.startswith("/"):
            command, _, arg = line.partition(" ")
            if command == "/quit":
                return
            candidate_id = _command(command, arg.strip(), candidate_id, llm, store, areas, clock, write)
            continue
        try:
            write(f"bot> {turn.handle_message(llm, store, areas, candidate_id, line, clock())}")
        except Exception:
            write("bot> " + phrase(llm, Directive(Kind.TECHNICAL_ERROR), "es"))


def _new(store, areas, clock, write) -> str:
    candidate_id = uuid.uuid4().hex[:8]
    write(f"[candidate {candidate_id}]")
    write(f"bot> {turn.start(store, areas, candidate_id, clock())}")
    return candidate_id


def _command(command, arg, candidate_id, llm, store, areas, clock, write) -> str:
    if command == "/new":
        return _new(store, areas, clock, write)
    if command == "/resume":
        if store.get(arg) is None:
            write(f"[candidate {arg or '?'} not found]")
            return candidate_id
        write(f"[resumed {arg}]")
        return arg
    if command == "/wait24h":
        reply = turn.wait_24h(llm, store, areas, candidate_id, clock())
        write(f"bot> {reply}" if reply else "[no reply: stalled or already finished]")
        return candidate_id
    write(f"[unknown command {command}] {HELP}")
    return candidate_id


def main() -> None:
    from sazon import gemini
    from sazon.llm import LLMError

    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        llm = gemini.from_env()
    except LLMError as error:
        sys.exit(str(error))
    if "--list-models" in sys.argv:
        print("\n".join(llm.models()))
        return
    print(f"Grupo Sazón screening chat (model {llm.model}). {HELP}\n")
    run(llm, Store(config.DB_PATH), config.AREAS)


if __name__ == "__main__":
    main()
