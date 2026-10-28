"""D52, D53, D56, D57 in the dashboard: login, the applications switch, the review queue and erasing data."""
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.support.paths import DASHBOARD
from sazon.client import SAZON_CALENDAR
from screener.model import RecruiterStatus
from screener.store import Store
from tests.support.dash import PASSWORD, login, logout, seed_accounts

APP = str(DASHBOARD)
NOW = datetime.now()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    return Store(path, calendar=SAZON_CALENDAR)


def candidate(store, cid, name, outcome="QUALIFIED", reasons=(), city="Madrid"):
    store.commit_turn(cid, NOW, {}, {"name": name, "city": city}, outcome, [("consent_given", "")],
                      [("candidate", f"soy {name}")], reasons=list(reasons), summary=f"{name} · {city}")


def fresh():
    at = AppTest.from_file(APP, default_timeout=10).run()
    assert not at.exception, at.exception
    return at


def signed_in(name="Ana"):
    at = login(fresh(), name)
    assert not at.exception, at.exception
    return at


def metrics(at):
    return {m.label: m.value for m in at.metric}


# --- login ------------------------------------------------------------------------------------------------------

def test_without_signing_in_nothing_but_the_login_form_is_shown(db):
    candidate(db, "c1", "Juan Pérez")
    at = fresh()
    assert at.text_input(key="login_password").proto.type == 1  # a password box: the text is hidden
    assert not at.dataframe and not at.metric and not at.selectbox
    assert "Juan" not in " ".join(str(e.value) for e in [*at.markdown, *at.text, *at.caption, *at.title])


def test_the_right_name_and_password_open_the_dashboard(db):
    candidate(db, "c1", "Juan Pérez")
    at = signed_in("ana")  # the name is matched ignoring case and shown as registered
    assert at.session_state["recruiter"] == "Ana" and at.dataframe and at.metric


@pytest.mark.parametrize("name,password", [("Ana", "mala-contraseña-1"), ("Nadie", PASSWORD), ("", ""), ("Ana", "")])
def test_a_wrong_login_is_refused_with_one_generic_message(db, name, password):
    at = login(fresh(), name, password)
    assert at.error and "incorrectos" in at.error[0].value
    assert "recruiter" not in at.session_state and not at.dataframe


def test_with_no_accounts_the_login_becomes_a_form_to_create_the_first_one_and_shows_nothing_else(db, tmp_path):
    (tmp_path / "recruiters.json").unlink()
    candidate(db, "c1", "Juan Pérez")
    at = fresh()
    assert at.text_input(key="setup_name") and at.text_input(key="setup_password").proto.type == 1
    assert "login_name" not in keys(at) and not at.dataframe and not at.metric
    assert "Juan" not in " ".join(str(e.value) for e in [*at.markdown, *at.text, *at.caption, *at.title])


def keys(at):
    return [box.key for box in at.text_input]


def create_first(at, name="Ana", password=PASSWORD, confirm=None):
    at.text_input(key="setup_name").set_value(name)
    at.text_input(key="setup_password").set_value(password)
    at.text_input(key="setup_confirm").set_value(password if confirm is None else confirm)
    at.form_submit_button(key="setup_submit").click().run()
    assert not at.exception, at.exception
    return at


def test_creating_the_first_account_signs_that_person_in_and_is_logged(db, tmp_path):
    from screener import accounts
    (tmp_path / "recruiters.json").unlink()
    at = create_first(fresh(), "Ana")
    assert at.session_state["recruiter"] == "Ana" and "setup_name" not in keys(at)
    assert accounts.verify(tmp_path / "recruiters.json", "Ana", PASSWORD) == "Ana"
    [entry] = [e for e in db.admin_log() if e.action == "account_created"]
    assert (entry.actor, entry.detail) == ("setup", "Ana")


@pytest.mark.parametrize("name,password,confirm,message", [
    ("Ana", PASSWORD, "otra-distinta-123", "no coinciden"), ("", PASSWORD, None, "nombre"), ("Ana", "corta", None, "al menos"),
])
def test_a_first_account_that_is_wrong_is_refused_and_nothing_is_created(db, tmp_path, name, password, confirm, message):
    from screener import accounts
    (tmp_path / "recruiters.json").unlink()
    at = create_first(fresh(), name, password, confirm)
    assert at.error and message in at.error[0].value and "recruiter" not in at.session_state
    assert not accounts.has_accounts(tmp_path / "recruiters.json")


def test_once_an_account_exists_the_login_page_offers_no_way_to_create_another(db):
    at = fresh()
    assert "setup_name" not in keys(at) and "login_name" in keys(at)


def add_recruiter(at, name, password=PASSWORD, confirm=None):
    at.sidebar.text_input(key="new_account_name").set_value(name)
    at.sidebar.text_input(key="new_account_password").set_value(password)
    at.sidebar.text_input(key="new_account_confirm").set_value(password if confirm is None else confirm)
    at.sidebar.button(key="new_account_submit").click().run()
    assert not at.exception, at.exception
    return at


def test_a_signed_in_recruiter_can_add_another_account_who_can_then_sign_in_and_it_is_logged(db):
    at = add_recruiter(signed_in("Ana"), "Marta")
    assert any("Marta" in str(s.value) for s in at.sidebar.success)
    assert [e.detail for e in db.admin_log() if e.actor == "recruiter:Ana" and e.action == "account_created"] == ["Marta"]
    assert signed_in("Marta").session_state["recruiter"] == "Marta"


@pytest.mark.parametrize("name,password,confirm,message", [
    ("ana", PASSWORD, None, "Ya hay una cuenta"), ("Marta", PASSWORD, "otra-distinta-123", "no coinciden"),
    ("Marta", "corta", None, "al menos"), ("", PASSWORD, None, "nombre"),
])
def test_adding_an_account_that_is_wrong_is_refused_and_nothing_is_logged(db, name, password, confirm, message):
    at = add_recruiter(signed_in("Ana"), name, password, confirm)
    assert any(message in str(e.value) for e in at.sidebar.error)
    assert not [e for e in db.admin_log() if e.action == "account_created"]


def test_the_free_text_name_box_is_gone_and_the_session_name_is_the_one_logged(db):
    candidate(db, "c1", "Juan Pérez")
    at = signed_in("Luis")
    assert all(box.key.startswith("new_account_") for box in at.sidebar.text_input)  # none to type who you are
    at.selectbox(key="candidate").select("c1").run()
    at.text_area(key="note").set_value("llamar mañana")
    at.form_submit_button(key="save_note").click().run()
    assert [n.author for n in db.notes("c1")] == ["Luis"]


def test_signing_out_returns_to_the_login_form(db):
    at = logout(signed_in())
    assert at.text_input(key="login_name") and not at.dataframe


# --- the applications switch ------------------------------------------------------------------------------------

def test_a_recruiter_can_close_and_reopen_applications_and_it_is_logged(db):
    at = signed_in("Ana")
    assert db.accepting_applications() is True
    at.sidebar.button(key="toggle_applications").click().run()
    assert db.accepting_applications() is False and any("CERRADAS" in str(c.value) for c in at.sidebar.caption)
    at.sidebar.button(key="toggle_applications").click().run()
    assert db.accepting_applications() is True
    assert [(e.actor, e.action) for e in db.admin_log()] == [("recruiter:Ana", "applications_closed"),
                                                             ("recruiter:Ana", "applications_opened")]


# --- the review queue (D52) -----------------------------------------------------------------------------------------

def test_agent_rejections_wait_in_a_review_queue_until_a_recruiter_sets_a_status(db):
    candidate(db, "r1", "Rechazada Licencia", "DISQUALIFIED", ["NO_LICENSE"])
    candidate(db, "r2", "Rechazada Zona", "DISQUALIFIED", ["OUT_OF_AREA"], city="Sevilla")
    candidate(db, "r3", "Fuera De Tema", "ENDED_OFF_TOPIC")
    candidate(db, "r4", "Sin Consentimiento", "DISQUALIFIED", ["NO_CONSENT"])
    candidate(db, "r5", "Revisada", "DISQUALIFIED", ["NO_LICENSE"])
    db.set_status("r5", RecruiterStatus.CONTACTED, "Ana", NOW)
    at = signed_in()
    assert metrics(at)["Descartes por revisar"] == "3"
    at.checkbox(key="f_review").check().run()
    assert sorted(at.dataframe[0].value["Id"]) == ["r1", "r2", "r3"]


def test_overruling_a_rejection_takes_it_out_of_the_queue(db):
    candidate(db, "r1", "Rechazada Licencia", "DISQUALIFIED", ["NO_LICENSE"])
    at = signed_in()
    at.selectbox(key="candidate").select("r1").run()
    at.selectbox(key="new_status").select("interview_scheduled")
    at.form_submit_button(key="save_status").click().run()
    assert metrics(at)["Descartes por revisar"] == "0"


# --- erasing data (D53) -----------------------------------------------------------------------------------------------

def test_erasing_needs_the_confirmation_box(db):
    candidate(db, "c1", "Juan Pérez")
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    at.button(key="erase_candidate").click().run()
    assert at.error and db.get("c1") is not None


def test_a_confirmed_erase_removes_the_candidate_and_leaves_an_anonymous_log(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    at = signed_in("Ana")
    at.selectbox(key="candidate").select("c1").run()
    at.checkbox(key="confirm_erase").check().run()
    at.button(key="erase_candidate").click().run()
    assert not at.exception, at.exception
    assert db.get("c1") is None and db.get("c2") is not None
    [entry] = [e for e in db.admin_log() if e.action == "candidate_erased"]
    assert entry.actor == "recruiter:Ana" and "reason=request" in entry.detail and "Juan" not in entry.detail
    assert list(at.dataframe[0].value["Id"]) == ["c2"]
    assert any("borrados" in str(s.value).lower() for s in at.success)


def test_the_erase_confirmation_does_not_stay_ticked_for_the_next_candidate(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    at.checkbox(key="confirm_erase").check().run()
    at.button(key="erase_candidate").click().run()
    at.selectbox(key="candidate").select("c2").run()
    assert at.checkbox(key="confirm_erase").value is False


# --- found by the architecture review ---------------------------------------------------------------------

def test_a_status_and_assignee_saved_for_one_candidate_do_not_carry_over_to_the_next(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    at.selectbox(key="new_status").select("hired")
    at.form_submit_button(key="save_status").click().run()
    at.text_input(key="assignee").set_value("Luis")
    at.form_submit_button(key="save_assignee").click().run()
    at.selectbox(key="candidate").select("c2").run()
    assert at.selectbox(key="new_status").value == "new" and at.text_input(key="assignee").value == ""
    at.form_submit_button(key="save_status").click().run()  # saving without touching anything
    assert db.recruiter("c2").status == RecruiterStatus.NEW and db.recruiter("c2").assignee is None


def test_a_note_typed_for_one_candidate_is_not_left_in_the_box_for_the_next(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    at.text_area(key="note").set_value("nota a medias")
    at.selectbox(key="candidate").select("c2").run()
    assert at.text_area(key="note").value == ""


def test_acting_on_a_candidate_erased_in_the_meantime_shows_a_message_instead_of_crashing(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    db.erase_candidate("c1", "recruiter:Luis", NOW, "request")
    at.selectbox(key="new_status").select("contacted")
    at.form_submit_button(key="save_status").click().run()
    assert not at.exception, at.exception
    assert any("ya no está en la lista" in str(w.value) for w in at.warning)
    assert db.get("c1") is None


def test_the_contact_hint_only_shows_for_qualified_candidates_nobody_has_contacted(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    db.set_status("c2", RecruiterStatus.CONTACTED, "Ana", NOW)
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    assert any("contáctalo" in str(e.value) for e in [*at.caption, *at.markdown, *at.text])
    at.selectbox(key="candidate").select("c2").run()
    assert not any("contáctalo" in str(e.value) for e in [*at.caption, *at.markdown, *at.text])


def test_signing_out_clears_everything_the_previous_recruiter_had_open(db):
    candidate(db, "c1", "Juan Pérez")
    at = signed_in("Ana")
    at.text_input(key="f_search").set_value("zzz").run()
    logout(at)
    login(at, "Luis")
    assert at.text_input(key="f_search").value == "" and at.session_state["recruiter"] == "Luis"
    assert at.selectbox(key="candidate").value is None
