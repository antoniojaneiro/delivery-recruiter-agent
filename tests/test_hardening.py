"""Weak points found by the whole-product review (D50)."""
import hashlib
import math
from datetime import date, datetime

import pytest

from sazon.client import SAZON_CALENDAR, SAZON_CLIENT
from screener import turn
from sazon import config
from screener.extraction import StartDate
from sazon.spec import SAZON, Extraction
from screener.llm import LLMError
from screener.phrasing import Directive, Kind, consent_message, phrase
from sazon.fields import Field
from screener.screening import Screening
from screener.store import Store
from screener.validators import match_city, validate_name
from sazon.validators import validate_experience
from tests.fakes import FakeLLM, ScriptedLLM

TODAY = date(2026, 10, 25)  # a Sunday
NOW = datetime(2026, 10, 25, 10, 0)


# --- start dates ------------------------------------------------------------------------------

@pytest.mark.parametrize("spec,expected", [
    ({"in_months": 3}, date(2027, 1, 25)),
    ({"in_months": 1}, date(2026, 11, 25)),
    ({"in_months": 4}, date(2027, 2, 25)),
    ({"weekday": 0}, date(2026, 10, 26)),      # next Monday (today is Sunday)
    ({"weekday": 6}, date(2026, 11, 1)),       # "el domingo" said on a Sunday: next week's, not today
    ({"weekday": 4}, date(2026, 10, 30)),
])
def test_months_and_weekdays_are_resolved_in_code(spec, expected):
    assert StartDate(**spec).resolve(TODAY) == expected


def test_a_month_that_is_shorter_clips_to_its_last_day():
    assert StartDate(in_months=1).resolve(date(2026, 1, 31)) == date(2026, 2, 28)


def test_the_extraction_accepts_months_and_weekdays():
    ex = Extraction.model_validate({"start_date": {"weekday": 2}})
    assert ex.start_date.weekday == 2


def test_the_prompt_tells_the_model_not_to_compute_these_dates_either():
    from sazon.spec import SYSTEM
    assert "in_months" in SYSTEM and "weekday" in SYSTEM


# --- experience years and names -------------------------------------------------------------

@pytest.mark.parametrize("years", [math.nan, math.inf, -math.inf, 61, 1000])
def test_impossible_years_are_refused(years):
    assert not validate_experience(years, ["glovo"]).ok


def test_a_long_career_is_accepted():
    assert validate_experience(30, ["glovo"]).ok


@pytest.mark.parametrize("name", ["Dr. Juan Pérez", "J. Pérez", "Juan P. Gil", "Dra. Ana Ruiz", "Mª Carmen Gil"])
def test_titles_and_initials_with_a_dot_are_valid_names(name):
    assert validate_name(name).ok


@pytest.mark.parametrize("name", ["Juan.", "J.", "Ju.an Pérez", "Juan Pérez 3", "..", "Juan  ."])
def test_stray_dots_are_still_refused(name):
    assert not validate_name(name).ok


# --- cities written the way people write them ----------------------------------------------------

@pytest.mark.parametrize("text,city", [
    ("Madrid, España", "Madrid"), ("madrid españa", "Madrid"), ("Guadalajara, Jalisco", "Guadalajara"),
    ("Barcelona (España)", "Barcelona"), ("Ciudad de México, México", "Ciudad de México"),
    ("Zapopan", "Guadalajara"), ("Zapopan, Jalisco", "Guadalajara"), ("Chamberí", "Madrid"),
    ("L'Hospitalet de Llobregat", "Barcelona"), ("Hospitalet", "Barcelona"), ("Coyoacán", "Ciudad de México"),
    ("San Pedro Garza García", "Monterrey"),
])
def test_places_with_a_country_or_state_and_nearby_towns_map_to_the_service_area(text, city):
    result = match_city(text, config.AREAS, SAZON.place_qualifiers)
    assert result.status == "match" and result.city == city


@pytest.mark.parametrize("text", ["Sevilla, España", "Bilbao", "Cancún, Quintana Roo", "Madrid, Texas"])
def test_places_that_really_are_outside_are_still_outside(text):
    assert match_city(text, config.AREAS, SAZON.place_qualifiers).status == "out_of_area"


# --- model-phrased text must not promise anything -------------------------------------------------

@pytest.mark.parametrize("promise", [
    "¡Genial! El sueldo es de 1200 € al mes. ¿Cuál es tu ciudad?", "Te pagamos 15$ la hora, ¿dónde vives?",
    "You will earn a good salary. Where do you live?", "¡Estás contratado! ¿Cuál es tu nombre?",
    "Te llamamos mañana a las 10:30. ¿Tienes licencia?", "We start Monday at 9h30, do you have a license?",
    "Ganarás 800 euros. ¿Tienes licencia?", "You are hired! What city?",
])
def test_a_phrased_reply_that_mentions_pay_a_hire_or_a_call_time_is_replaced_by_the_fixed_question(promise):
    language = "en" if promise.split()[0] in {"You", "We"} else "es"
    out = phrase(FakeLLM(promise), SAZON, Directive(Kind.ASK, field=Field.LICENSE), language)
    assert out != promise


def test_an_ordinary_question_with_a_number_in_it_is_kept():
    text = "¿Cuántos años de experiencia tienes, 1 o 2?"
    assert phrase(FakeLLM(text), SAZON, Directive(Kind.ASK, field=Field.EXPERIENCE), "es") == text


# --- consent evidence and failure traces ---------------------------------------------------------

def test_the_consent_event_records_which_wording_was_accepted():
    s = Screening(config.AREAS, SAZON)
    s.record_consent(True)
    kind, detail = s.events[0]
    assert kind == "consent_given"
    assert detail == "text_sha256=" + hashlib.sha256(consent_message(SAZON).encode("utf-8")).hexdigest()[:12]


def test_declining_also_records_the_wording_that_was_shown():
    s = Screening(config.AREAS, SAZON)
    s.record_consent(False)
    assert s.events[0][1].startswith("text_sha256=")


def test_an_llm_error_exposes_a_short_kind_without_the_message_content():
    assert LLMError("RateLimitError: Error code: 429 - {...}").kind == "RateLimitError"
    assert LLMError("the model returned an empty answer").kind == "LLMError"


def test_a_model_failure_event_says_what_kind_of_failure_it_was(tmp_path):
    store = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    turn.start(store, SAZON_CLIENT, "c1", NOW)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "sí", NOW)
    llm = ScriptedLLM([LLMError("NotFoundError: models/x is not found for API version v1")])
    turn.handle_message(llm, store, SAZON_CLIENT, "c1", "Juan Pérez", NOW)
    [failure] = [e for e in store.events("c1") if e.type == "model_failure"]
    assert failure.detail == "unreachable:NotFoundError"


# --- operations ---------------------------------------------------------------------------------

def run_chat(store, lines):
    from screener import chat

    out, feed = [], iter(lines)

    def read(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    chat.run(ScriptedLLM(), store, SAZON_CLIENT, read=read, write=out.append, clock=lambda: NOW)
    return out


def test_a_new_candidate_never_reuses_an_existing_id(tmp_path, monkeypatch):
    from screener import chat

    draws = iter(["aaaaaaaaaaaa", "aaaaaaaaaaaa", "aaaaaaaaaaaa", "bbbbbbbbbbbb"])
    monkeypatch.setattr(chat, "_draw_id", lambda: next(draws))
    store = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    run_chat(store, ["/new", "/quit"])
    assert sorted(r.candidate_id for r in store.list_candidates()) == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


def test_ids_are_long_enough_to_make_collisions_negligible():
    from screener import chat

    assert len(chat._draw_id()) >= 12 and chat._draw_id() != chat._draw_id()


def test_the_chat_and_the_dashboard_use_the_same_database_file(tmp_path, monkeypatch):
    from screener import chat
    from sazon import chat as sazon_chat

    target = tmp_path / "shared" / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(target))
    seen = {}
    monkeypatch.setattr("screener.gemini.from_env", lambda: type("L", (), {"model": "m"})())
    monkeypatch.setattr(chat, "run", lambda llm, store, areas, **kw: seen.update(path=store._path))
    monkeypatch.setattr("sys.argv", ["sazon.chat"])
    sazon_chat.main()
    assert seen["path"] == str(target)


def test_the_database_uses_wal_and_has_indexes_for_the_dashboard_queries(tmp_path):
    import sqlite3

    path = tmp_path / "s.db"
    Store(path, calendar=SAZON_CALENDAR)
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_events_candidate", "idx_messages_candidate", "idx_notes_candidate", "idx_slots_country_start",
            "idx_candidates_outcome"} <= names
    db.close()


def test_a_state_saved_by_an_older_version_still_loads_with_safe_defaults():
    old = {"consent": True, "values": {"name": "Juan Pérez"}}
    s = Screening.from_state(config.AREAS, old, SAZON)
    assert s.consent is True and s.values["name"] == "Juan Pérez"
    assert s.decide().outcome == "IN_PROGRESS" and s.next_field() == "experience"
    assert Screening.from_state(config.AREAS, {}, SAZON).consent is None


def test_a_state_with_unknown_extra_keys_from_a_newer_version_is_tolerated():
    s = Screening.from_state(config.AREAS, {"consent": True, "values": {}, "something_new": [1, 2, 3]}, SAZON)
    assert s.consent is True
