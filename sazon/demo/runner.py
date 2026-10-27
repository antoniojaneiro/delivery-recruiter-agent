"""Plays scripted candidate conversations through the real agent so a person can read its replies.

    python -m sazon.demo --list
    python -m sazon.demo --only happy_es,car_not_license
    python -m sazon.demo                      # all scenarios (about 2 model calls per message)

It uses a throw-away database (never the real one), real Gemini calls (so use the key in .env) and writes
the transcripts to data/demo/transcripts.md. The candidates are fictional."""
import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from screener import turn
from sazon import config
from sazon.demo.scenarios import BY_NAME, SCENARIOS, Scenario
from sazon.client import SAZON_CLIENT
from screener.store import Store

TECHNICAL_PROBLEM = ("problema técnico", "technical problem")
PAUSE_SECONDS = 4  # the free tier allows only a handful of requests per minute
RETRY_WAIT_SECONDS = 40


@dataclass
class Turn:
    you: str | None  # None for the agent's opening message
    bot: str


@dataclass
class Result:
    scenario: Scenario
    candidate_id: str
    turns: list[Turn] = field(default_factory=list)
    outcome: str | None = None
    extracted: dict = field(default_factory=dict)
    summary: str = ""
    booking: str = ""


def seed_slots(store: Store, now: datetime) -> list[int]:
    """Three slots a few days ahead in each country, so the booking flow can be seen."""
    base = (now + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    plan = [("ES", 10), ("ES", 12), ("ES", 17), ("MX", 9), ("MX", 11), ("MX", 16)]
    return [store.add_slot(country, base + timedelta(days=i // 2 + (i % 2), hours=hour), "Demo", "Demo", now)
            for i, (country, hour) in enumerate(plan)]


def _show(write, prefix: str, text: str) -> None:
    first, *rest = text.splitlines() or [""]
    write(f"{prefix}> {first}")
    for line in rest:
        write("      " + line)


def run_scenario(llm, store: Store, scenario: Scenario, now: datetime, pause: float, write,
                 retry_wait: float = 0) -> Result:
    candidate_id = f"demo-{scenario.name}"
    result = Result(scenario, candidate_id)
    write(f"\n=== {scenario.title} [{scenario.name}] ===")
    opening = turn.start(store, SAZON_CLIENT, candidate_id, now)
    result.turns.append(Turn(None, opening))
    _show(write, "bot", opening)
    for message in scenario.messages:
        time.sleep(pause)
        _show(write, "you", message)
        reply = turn.handle_message(llm, store, SAZON_CLIENT, candidate_id, message, now)
        if retry_wait and any(marker in reply for marker in TECHNICAL_PROBLEM):
            time.sleep(retry_wait)  # most likely the rate limit; a failed turn costs the candidate nothing (D39)
            reply = turn.handle_message(llm, store, SAZON_CLIENT, candidate_id, message, now)
        result.turns.append(Turn(message, reply))
        _show(write, "bot", reply)
    record = store.get(candidate_id)
    result.outcome, result.extracted, result.summary = record.outcome, record.extracted, record.summary or ""
    if record.booking:
        result.booking = f"{record.booking.starts_at:%Y-%m-%d %H:%M} ({record.booking.country})"
    write(f"--- outcome: {result.outcome}" + (f" · call booked {result.booking}" if result.booking else ""))
    write(f"--- data: {result.extracted}")
    return result


def to_markdown(results: list[Result]) -> str:
    lines = ["# Respuestas del agente por escenario", "",
             "Conversaciones ficticias jugadas contra el agente real (modelo incluido).", ""]
    for result in results:
        lines += [f"## {result.scenario.title}", ""]
        if result.scenario.note:
            lines += [f"_{result.scenario.note}_", ""]
        for t in result.turns:
            if t.you is not None:
                lines += [f"**Candidato:** {t.you}", ""]
            lines += [f"**Agente:** {t.bot}".replace("\n", "  \n"), ""]
        lines += [f"Resultado: {result.outcome}" + (f" · llamada {result.booking}" if result.booking else ""), "",
                  f"Datos: `{result.extracted}`", ""]
        if result.summary:
            lines += ["Resumen para el reclutador:", ""] + [f"> {line}" for line in result.summary.splitlines()] + [""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sazon.demo", description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="show the scenarios and exit")
    parser.add_argument("--only", help="comma-separated scenario names")
    parser.add_argument("--pause", type=float, default=PAUSE_SECONDS, help="seconds between messages")
    parser.add_argument("--out", default=str(config.DEMO_DIR / "transcripts.md"), help="where to write the transcripts")
    args = parser.parse_args(argv)

    if args.list:
        for s in SCENARIOS:
            print(f"{s.name:26} {s.title}")
        return
    names = [n.strip() for n in args.only.split(",")] if args.only else [s.name for s in SCENARIOS]
    unknown = [n for n in names if n not in BY_NAME]
    if unknown:
        sys.exit(f"Unknown scenario: {', '.join(unknown)}. Use --list to see the names.")

    from screener import gemini
    from screener.llm import LLMError

    try:
        llm = gemini.from_env()
    except LLMError as error:
        sys.exit(str(error))
    now = datetime.now()
    results = []
    with TemporaryDirectory() as folder:
        store = Store(Path(folder) / "demo.db", calendar=SAZON_CLIENT.calendar)
        seed_slots(store, now.astimezone())
        for name in names:
            results.append(run_scenario(llm, store, BY_NAME[name], now, args.pause, print, RETRY_WAIT_SECONDS))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(results), encoding="utf-8")
    print(f"\nTranscripts written to {out}\n")
    for r in results:
        print(f"{r.scenario.name:26} {r.outcome}" + (f"  call {r.booking}" if r.booking else ""))

