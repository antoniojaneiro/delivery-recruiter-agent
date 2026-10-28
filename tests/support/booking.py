"""Helpers for the tests that take a candidate through the screening to a call offer (D48)."""
from datetime import datetime

from sazon import config
from screener import turn
from tests.support.clients import client_for
from tests.support.fakes import ScriptedLLM

AREAS = config.AREAS
NOW = datetime(2026, 10, 25, 10, 0)
NOW_AWARE = NOW.astimezone()  # the same instant, for the store-level calls

ES_SLOTS = [datetime(2026, 11, 3, 10, 0), datetime(2026, 11, 4, 9, 30), datetime(2026, 11, 5, 16, 0)]
MX_SLOT = datetime(2026, 11, 3, 9, 0)


def say(store, message, *extractions, cid="c1"):
    llm = ScriptedLLM(extractions)
    return turn.handle_message(llm, store, client_for(AREAS), cid, message, NOW), llm


def qualify(store, cid="c1", city="Madrid", language="sí", english=False):
    """The candidate answers in Spanish, or in English when `english` (the chat language follows their words)."""
    turn.start(store, client_for(AREAS), cid, NOW)
    es = [("Soy Juan Pérez", "2 años con Glovo", "tiempo completo", "mañanas", "ya mismo", "sí tengo"),
          ("I'm John Smith", "2 years with Glovo", "full time", "mornings", "right now", "yes I do")][english]
    say(store, language, cid=cid)
    say(store, es[0], {"name": "Juan Pérez"}, cid=cid)
    say(store, es[1], {"experience_years": 2, "platforms": ["Glovo"]}, cid=cid)
    say(store, es[2], {"availability": ["full_time"]}, cid=cid)
    say(store, es[3], {"schedule": "morning"}, cid=cid)
    say(store, es[4], {"start_date": {"now": True}}, cid=cid)
    say(store, city, {"city": city}, cid=cid)
    return say(store, es[5], {"has_license": True}, cid=cid)[0]


def add_slots(store, country="ES", times=ES_SLOTS):
    """One free time each; a recruiter takes one call at a time, so a time given twice is a second recruiter."""
    return [store.add_slot(country, t, "Ana" + (str(times[:i].count(t) + 1) if t in times[:i] else ""), "Ana", NOW_AWARE)
            for i, t in enumerate(times)]


def booked(store, cid="c1"):
    return store.booking_of(cid)
