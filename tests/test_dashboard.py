"""The Streamlit recruiter dashboard, driven in-process with AppTest (no browser)."""
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from sazon.client import SAZON_CALENDAR
from screener.model import RecruiterStatus
from screener.store import Store
from tests.dash import login, logout, seed_accounts

T1 = datetime(2026, 10, 25, 10, 0)
APP = str(Path(__file__).resolve().parent.parent / "dashboard.py")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    return Store(path, calendar=SAZON_CALENDAR)


def seed(store):
    def add(cid, name, city, outcome, summary, reasons=(), messages=(), events=()):
        extracted = {k: v for k, v in (("name", name), ("city", city)) if v}
        store.commit_turn(cid, T1, {}, extracted, outcome, list(events), list(messages),
                          reasons=list(reasons), summary=summary)

    add("c1", "Juan Pérez", "Madrid", "QUALIFIED", "Juan Pérez · Madrid · Cualificado\nLicencia: sí",
        messages=[("agent", "Hola, soy el asistente virtual"), ("candidate", "sí"), ("agent", "¿Cómo te llamas?")],
        events=[("consent_given", ""), ("field_accepted", "name")])
    add("c2", "María García-López", "Guadalajara", "QUALIFIED", "María García-López · Guadalajara · Cualificado")
    add("c3", "Ana Ruiz", "Sevilla", "DISQUALIFIED", "Ana Ruiz · Sevilla · Descartado por el agente",
        reasons=["OUT_OF_AREA"])
    add("c4", None, None, "BLOCKED", "Candidato sin nombre · Bloqueado", reasons=["BLOCKED_ON_NAME"])
    store.set_status("c2", RecruiterStatus.CONTACTED, "Ana", T1)


def run(as_user="Ana"):
    at = AppTest.from_file(APP, default_timeout=10).run()
    login(at, as_user)
    assert not at.exception, at.exception
    return at


def rows(at):
    return at.dataframe[0].value


def metrics(at):
    return {m.label: m.value for m in at.metric}


def choose(at, candidate_id):
    at.selectbox(key="candidate").select(candidate_id).run()
    assert not at.exception, at.exception
    return at


def texts(at):
    return "\n".join(str(e.value) for e in [*at.text, *at.markdown, *at.caption, *at.code])


def test_an_empty_database_says_so_instead_of_showing_an_empty_table(db):
    at = run()
    assert any("No hay candidatos" in str(i.value) for i in at.info)


def test_the_key_numbers_and_the_candidate_table_are_shown(db):
    seed(db)
    at = run()
    assert metrics(at) == {"Candidatos": "4", "Cualificados por contactar": "1", "Descartes por revisar": "1",
                           "Bloqueados": "1", "Sin respuesta": "0"}
    assert sorted(rows(at)["Id"]) == ["c1", "c2", "c3", "c4"]
    assert set(rows(at).columns) >= {"Id", "Nombre", "Ciudad", "Agente", "Reclutador", "Asignado a", "Actualizado"}


def test_filtering_by_the_agents_outcome_and_the_recruiters_status(db):
    seed(db)
    at = run()
    at.multiselect(key="f_outcome").select("QUALIFIED").run()
    assert sorted(rows(at)["Id"]) == ["c1", "c2"]
    at.multiselect(key="f_status").select("new").run()
    assert list(rows(at)["Id"]) == ["c1"]


def test_search_ignores_accents_and_case(db):
    seed(db)
    at = run()
    at.text_input(key="f_search").set_value("GARCIA lopez").run()
    assert list(rows(at)["Id"]) == ["c2"]


def test_no_match_says_so(db):
    seed(db)
    at = run()
    at.text_input(key="f_search").set_value("zzz").run()
    assert any("Ningún candidato" in str(i.value) for i in at.info)


def test_choosing_a_candidate_shows_the_summary_the_conversation_and_the_audit_log(db):
    seed(db)
    at = choose(run(), "c1")
    shown = texts(at)
    assert "Juan Pérez · Madrid · Cualificado" in shown and "Licencia: sí" in shown
    chat = [(m.name, m.text[0].value) for m in at.chat_message]
    assert chat == [("assistant", "Hola, soy el asistente virtual"), ("user", "sí"), ("assistant", "¿Cómo te llamas?")]
    events = next(df.value for df in at.dataframe[1:] if "Tipo" in df.value.columns)
    assert list(events["Tipo"]) == ["consent_given", "field_accepted"]



def test_a_recruiter_can_change_the_status_and_it_is_logged_with_their_name(db):
    seed(db)
    at = run()
    choose(at, "c1")
    at.selectbox(key="new_status").select("interview_scheduled")
    at.form_submit_button(key="save_status").click().run()
    assert not at.exception, at.exception
    assert db.recruiter("c1").status == RecruiterStatus.INTERVIEW_SCHEDULED
    assert [e.actor for e in db.events("c1") if e.type == "recruiter_status"] == ["recruiter:Ana"]
    assert metrics(at)["Cualificados por contactar"] == "0"


def test_a_recruiter_can_assign_and_add_notes(db):
    seed(db)
    at = run()
    choose(at, "c1")
    at.text_input(key="assignee").set_value("Luis")
    at.form_submit_button(key="save_assignee").click().run()
    at.text_area(key="note").set_value("Llamé, volverá a llamar")
    at.form_submit_button(key="save_note").click().run()
    assert not at.exception, at.exception
    assert db.recruiter("c1").assignee == "Luis"
    assert [(n.author, n.text) for n in db.notes("c1")] == [("Ana", "Llamé, volverá a llamar")]
    assert "Llamé, volverá a llamar" in texts(at)


def test_an_empty_note_is_refused(db):
    seed(db)
    at = run()
    choose(at, "c1")
    at.text_area(key="note").set_value("   ")
    at.form_submit_button(key="save_note").click().run()
    assert at.error and db.notes("c1") == []


def test_a_recruiter_may_overrule_the_agents_rejection(db):
    seed(db)
    at = run()
    choose(at, "c3")
    at.selectbox(key="new_status").select("interview_scheduled")
    at.form_submit_button(key="save_status").click().run()
    assert db.recruiter("c3").status == RecruiterStatus.INTERVIEW_SCHEDULED
    assert db.get("c3").outcome == "DISQUALIFIED"


EVIL = "![tracker](http://evil.example/pixel.png) [click here](http://evil.example/login) **bold** <b>x</b>"


def test_candidate_text_is_shown_as_plain_text_never_as_markdown_or_html(db):
    seed(db)
    db.commit_turn("c1", T1, {}, {"name": "Juan Pérez"}, "QUALIFIED", [], [("candidate", EVIL)])
    at = choose(run(), "c1")
    shown = [m for m in at.chat_message if any(EVIL == t.value for t in m.text)]
    assert shown, "the message must be a plain text element"
    assert not any(EVIL in str(md.value) for md in at.markdown)


def test_a_recruiters_note_and_name_are_shown_as_plain_text(db):
    seed(db)
    db.add_note("c1", EVIL, "**Ana**", T1)
    at = choose(run(), "c1")
    assert any(EVIL == t.value for t in at.text)
    assert any(t.value.startswith("**Ana** · ") for t in at.text)
    assert not any("evil.example" in str(md.value) or "**Ana** ·" in str(md.value) for md in at.markdown)


def test_the_dashboard_only_listens_on_this_machine():
    import tomllib
    config = tomllib.loads((Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["address"] == "localhost"
    assert config["browser"]["gatherUsageStats"] is False


def test_clicking_a_row_in_the_table_opens_that_candidate_and_the_list_below_still_works(db):
    seed(db)
    at = run()
    second = rows(at).iloc[1]["Id"]
    at.session_state["candidate_table"] = {"selection": {"rows": [1], "columns": [], "cells": []}}
    at.run()
    assert not at.exception, at.exception
    assert at.selectbox(key="candidate").value == second
    other = next(i for i in ("c1", "c2", "c3", "c4") if i != second)
    at.selectbox(key="candidate").select(other).run()  # picking from the list is not undone by the old table click
    assert at.selectbox(key="candidate").value == other


def test_the_selected_candidate_shows_colored_status_badges(db):
    seed(db)
    at = choose(run(), "c2")
    markdown = " ".join(str(m.value) for m in at.markdown)
    assert ":green-badge[Cualificado]" in markdown and ":violet-badge[Contactado]" in markdown
