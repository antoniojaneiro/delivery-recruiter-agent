"""D75: a busy day against a real server. Candidates talk, some send a message twice at the same moment, and the model
is slow (1 to 3 seconds a call) and sometimes fails. Passing means every candidate ends where their answers put them,
nobody is lost, duplicated or double-booked, no request fails with a server error, and replies stay within a bound.

What "the real peak" means here (assumptions): 1000 applications a week, a fifth of them in the busiest 2 hours, about
10 messages each: 200 chats and 2000 messages in 7200 s, about 0.3 messages a second with 8 to 17 chats open at once.
  - the busy-day test: 200 candidates arriving over 150 s, ten seconds between messages: about 7 requests a second,
    roughly 25 times that peak;
  - the burst test: all 200 in the same instant;
  - the small test (every run of the normal suite): 10 candidates with the delays scaled down, so the server path is
    exercised on every run.

The big two are marked `load`: `python -m pytest -m load -q -s` prints the report."""
import json
import os
import random
import re
import socket
import sqlite3
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import httpx
import pytest
import uvicorn

from sazon import config
from sazon.spec import SAZON
from screener.llm import LLMError
from screener.phrasing import technical_error_message
from screener.service import create_app
from screener.store import Store
from tests.support.clients import client_for

CANDIDATES = 200
P95_BOUND_SECONDS = 10.0  # two model calls of up to 3 s per message, plus waiting for a free thread
DELAY_SCALE = float(os.environ.get("LOAD_DELAY_SCALE", "1"))  # 0.1 for a quick run while developing
FAILURE_RATE = 0.03  # model calls that fail; the candidate must never notice more than a repeated question

EXTRACTIONS = {  # what the model would read from each message
    "Soy Juan Pérez": {"name": "Juan Pérez"},
    "2 años con Glovo": {"experience_years": 2, "platforms": ["Glovo"]},
    "tiempo completo": {"availability": ["full_time"]},
    "mañanas": {"schedule": "morning"},
    "ya mismo": {"start_date": {"now": True}},
    "Madrid": {"city": "Madrid"},
    "Guadalajara": {"city": "Guadalajara"},
    "Sevilla": {"city": "Sevilla"},
    "sí tengo": {"has_license": True},
    "no tengo licencia": {"has_license": False},
    "correcto": {"confirms_rejection": True},
    "sí, vivo en Sevilla": {"confirms_rejection": True},
}
START = ["sí", "Soy Juan Pérez", "2 años con Glovo", "tiempo completo", "mañanas", "ya mismo"]
QUALIFIED_ES = [*START, "Madrid", "sí tengo"]
QUALIFIED_MX = [*START, "Guadalajara", "sí tengo"]
NO_LICENSE = [*START, "Madrid", "no tengo licencia", "correcto"]
OUT_OF_AREA = [*START, "Sevilla", "sí, vivo en Sevilla"]
WITHDRAWS = ["sí", "Soy Juan Pérez", "me retiro"]


def mix(n):
    """About a fifth qualify (the brief says 80% of applicants do not); the rest end in the other ways."""
    es, mx, no_license, out = round(n * 0.15), max(1, round(n * 0.05)), round(n * 0.4), round(n * 0.25)
    cases = ([("QUALIFIED", QUALIFIED_ES)] * es + [("QUALIFIED", QUALIFIED_MX)] * mx
             + [("DISQUALIFIED", NO_LICENSE)] * no_license + [("DISQUALIFIED", OUT_OF_AREA)] * out)
    return cases + [("WITHDRAWN", WITHDRAWS)] * (n - len(cases))


class SlowModel:
    """Stateless, so any number of candidates can use it: reads the message from the prompt, waits, answers."""

    def __init__(self, scale=1.0, seed=7):
        self.scale = scale
        self.random = random.Random(seed)
        self.lock = threading.Lock()
        self.calls = 0

    def complete(self, system, user, json_mode=False):
        with self.lock:
            self.calls += 1
            delay, fails = self.random.uniform(1, 3) * self.scale, self.random.random() < FAILURE_RATE
        time.sleep(delay)  # blocks the thread like a real network call
        if fails:
            raise LLMError("injected failure")
        if not json_mode:
            raise LLMError("no free wording: the fixed text is used")
        found = re.search(r"<candidate_message>\n(.*?)\n</candidate_message>", user, re.S)
        return json.dumps(EXTRACTIONS.get(found.group(1) if found else "", {}))


class Server:
    def __init__(self, app):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.sock]}, daemon=True)

    def __enter__(self):
        self.thread.start()
        while not self.server.started:
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *_):
        self.server.should_exit = True
        self.thread.join(timeout=15)


def add_call_times(store, now, days=30):
    for day in range(1, days + 1):  # more call times than qualified candidates, as a recruiter team would add
        for hour in range(9, 14):
            for country in ("ES", "MX"):
                at = (now + timedelta(days=day)).replace(hour=hour, minute=0, second=0, microsecond=0)
                store.add_slot(country, at, "Ana", "Ana", now.astimezone())


def run_day(tmp_path, spread, think, candidates=CANDIDATES, scale=DELAY_SCALE):
    """Candidates arrive over `spread` seconds and wait `think` seconds (a range) between messages; `scale` shrinks
    every wait, the model's included."""
    now = datetime.now()
    client = client_for(config.AREAS)
    store = Store(tmp_path / "load.db", calendar=client.calendar)
    add_call_times(store, now, days=30 if candidates >= 100 else 3)  # each call time is one disk commit
    model = SlowModel(scale)
    app = create_app(client, store, model, clock=datetime.now, log_path=tmp_path / "errors.log")
    latencies, statuses, problems, results, resets = [], [], [], {}, []
    guard = threading.Lock()
    pacing = random.Random(11)

    def call(http, url, **kwargs):
        """One request, sent again after a 503 (the server asking to retry later); latency counts the whole wait."""
        started = time.perf_counter()
        for _ in range(40):
            try:
                response = http.post(url, **kwargs)
            except httpx.TransportError:  # the server closed an idle connection just as it was reused: send again
                with guard:
                    resets.append(1)
                continue
            with guard:
                statuses.append(response.status_code)
            if response.status_code not in (503, 409):  # asked to retry later, or the first copy is still running
                break
            time.sleep(2 * scale + 0.2)
        with guard:
            latencies.append(time.perf_counter() - started)
            if response.status_code >= 400:
                problems.append(f"{response.status_code} {response.text[:200]}")
        return response

    def pause():
        with guard:
            wait = pacing.uniform(*think)
        time.sleep(wait * scale)

    def candidate(expected, lines, arrives):
        time.sleep(arrives * scale)
        with httpx.Client(base_url=base, timeout=120) as http:
            begun = call(http, "/candidates").json()
            cid, auth = begun["candidate_id"], {"Authorization": f"Bearer {begun['token']}"}
            url = f"/candidates/{cid}/messages"
            apology = technical_error_message(SAZON, "es")
            for number, line in enumerate(lines):
                pause()
                for again in range(5):  # a failed model call shows an apology; the person writes the same thing again
                    body = {"message_id": f"m{number}-{again}", "text": line}
                    if number % 5 == 4:  # a double tap: the same message twice at the same moment
                        with ThreadPoolExecutor(2) as pair:
                            twins = [pair.submit(call, http, url, json=body, headers=auth) for _ in range(2)]
                            first, second = [t.result().json() for t in twins]
                        if first != second:
                            problems.append(f"{cid}: the two copies got different answers")
                    else:
                        first = call(http, url, json=body, headers=auth).json()
                    if first.get("reply") != apology:
                        break
            if expected == "QUALIFIED":
                for attempt in range(20):  # a time another candidate took first is replaced by new options
                    if store.booking_of(cid):
                        break
                    pause()
                    with guard:
                        choice = str(pacing.randint(1, 3))
                    call(http, url, json={"message_id": f"pick{attempt}", "text": choice}, headers=auth)
        with guard:
            results[cid] = (expected, lines)

    with Server(app) as base:
        started = time.perf_counter()
        cases = mix(candidates)
        with ThreadPoolExecutor(candidates) as pool:
            arrivals = [pacing.uniform(0, spread) for _ in cases]
            for future in [pool.submit(candidate, *case, when) for case, when in zip(cases, arrivals)]:
                future.result()
        elapsed = time.perf_counter() - started

    ordered = sorted(latencies)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    print(f"\nrequests {len(latencies)} (sent {len(statuses)}), model calls {model.calls}, wall time {elapsed:.0f}s")
    print(f"latency median {statistics.median(ordered):.2f}s, p95 {p95:.2f}s, max {ordered[-1]:.2f}s")
    print(f"busy answers (503 or 409, retried) {statuses.count(503) + statuses.count(409)}, server errors {sum(s >= 500 and s != 503 for s in statuses)}, "
          f"connections reset and resent {len(resets)}")
    check(store, results, problems, candidates)
    return p95, statuses


def check(store, results, problems, candidates):
    assert len(results) == candidates
    assert not problems, problems[:5]
    booked = set()
    for cid, (expected, lines) in results.items():
        assert store.get(cid).outcome == expected, (cid, store.get(cid).outcome)
        if expected == "QUALIFIED":
            booking = store.booking_of(cid)
            assert booking is not None, f"{cid} qualified but has no call"
            assert booking.slot_id not in booked, "a call time was given twice"
            booked.add(booking.slot_id)
        assert len(store.messages(cid)) > len(lines), (cid, "a message was lost")
    # every message id that got an answer was applied once: resent copies and retries add no second candidate message
    with sqlite3.connect(store._path) as db:
        off = db.execute("""SELECT c.candidate_id FROM candidates c WHERE
            (SELECT COUNT(*) FROM replies r WHERE r.candidate_id = c.candidate_id AND r.reply IS NOT NULL) !=
            (SELECT COUNT(*) FROM messages m WHERE m.candidate_id = c.candidate_id AND m.role = 'candidate')""").fetchall()
    assert not off, f"{len(off)} candidates have a message applied twice or an answer not recorded: {off[:3]}"


def test_a_small_day_runs_on_a_real_server_in_every_test_run(tmp_path):
    _, statuses = run_day(tmp_path, spread=2, think=(0.5, 1.5), candidates=10, scale=0.02)
    assert not [s for s in statuses if s >= 500 and s != 503]


@pytest.mark.load
def test_a_busy_day_at_about_25_times_the_real_peak(tmp_path):
    p95, statuses = run_day(tmp_path, spread=150, think=(6, 16))
    assert statuses.count(503) + statuses.count(409) == 0, "the server asked callers to retry"
    assert p95 <= P95_BOUND_SECONDS, f"p95 {p95:.2f}s is over {P95_BOUND_SECONDS}s"


@pytest.mark.load
def test_everyone_arriving_in_the_same_instant_is_slowed_down_but_never_lost(tmp_path):
    run_day(tmp_path, spread=0, think=(0, 0))  # asks callers to retry; every conversation still ends correctly
