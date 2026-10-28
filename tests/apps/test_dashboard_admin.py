"""D52, D53, D56, D80 in the dashboard: login, the applications switch, the review queue and erasing data."""
from datetime import datetime
from pathlib import Path

import pytest

from tests.support.tables import table
from streamlit.testing.v1 import AppTest

from tests.support.paths import DASHBOARD
from sazon.client import SAZON_CALENDAR
from screener.model import RecruiterStatus
from screener.store import Store
from tests.support.dash import book_as_candidate, MANAGER_EMAIL, PASSWORD, login, login_manager, logout, seed_accounts, set_manager

APP = str(DASHBOARD)
NOW = datetime.now()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
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


# --- login (D80) ------------------------------------------------------------------------------------------------

def test_without_signing_in_nothing_but_the_login_form_is_shown(db):
    candidate(db, "c1", "Juan Pérez")
    at = fresh()
    assert at.text_input(key="login_password").proto.type == 1  # a password box: the text is hidden
    assert not at.dataframe and not at.metric and not at.selectbox
    assert "Juan" not in " ".join(str(e.value) for e in [*at.markdown, *at.text, *at.caption, *at.title])


def test_the_right_email_and_password_open_the_dashboard_whatever_the_case_of_the_email(db):
    candidate(db, "c1", "Juan Pérez")
    at = signed_in("ANA")  # ANA@sazon.test: an email is not case sensitive
    assert at.session_state["recruiter"] == "ana@sazon.test" and at.session_state["recruiter_name"] == "Ana"
    assert at.dataframe and at.metric


@table("name,password", [("Ana", "mala-contraseña-1"), ("Nadie", PASSWORD), ("", ""), ("Ana", "")])
def test_a_wrong_login_is_refused_with_one_generic_message(db, name, password):
    at = login(fresh(), name, password)
    assert at.error and "incorrectos" in at.error[0].value
    assert "recruiter" not in at.session_state and not at.dataframe


def test_the_login_page_has_no_sign_up_only_an_email_and_a_password(db):
    at = fresh()
    assert [box.key for box in at.text_input] == ["login_email", "login_password"] and not at.tabs


def test_with_no_manager_and_no_recruiters_the_page_says_how_to_set_one_up(db, tmp_path, monkeypatch):
    empty = tmp_path / "empty.db"
    monkeypatch.setenv("SAZON_DB", str(empty))
    at = fresh()
    assert any("HIRING_MANAGER_EMAIL" in str(w.value) for w in at.warning)


def test_five_wrong_passwords_lock_the_email_and_say_so(db):
    at = fresh()
    for _ in range(5):
        login(at, "Ana", "mala-contraseña-1")
    login(at, "Ana")  # even the right one, now
    assert at.error and "Demasiados intentos" in at.error[0].value and "recruiter" not in at.session_state


def test_signing_out_returns_to_the_login_form(db):
    at = logout(signed_in())
    assert at.text_input(key="login_email") and not at.dataframe


def test_the_free_text_name_box_is_gone_and_the_session_email_is_the_one_logged(db):
    candidate(db, "c1", "Juan Pérez")
    at = signed_in("Luis")
    assert not at.sidebar.text_input or all(box.key in {"old_password", "new_password", "new_password_again"}
                                            for box in at.sidebar.text_input)  # no box to type who you are
    at.selectbox(key="candidate").select("c1").run()
    at.text_area(key="note").set_value("llamar mañana")
    at.form_submit_button(key="save_note").click().run()
    assert [n.author for n in db.notes("c1")] == ["luis@sazon.test"]


# --- a recruiter changes their own password ---------------------------------------------------------------------

def change_password(at, old, new, again=None):
    at.text_input(key="old_password").set_value(old)
    at.text_input(key="new_password").set_value(new)
    at.text_input(key="new_password_again").set_value(new if again is None else again)
    at.form_submit_button(key="change_password").click().run()
    assert not at.exception, at.exception
    return at


def test_a_recruiter_changes_their_password_and_signs_in_with_the_new_one(db):
    at = change_password(signed_in("Ana"), PASSWORD, "otra-contraseña-9")
    assert at.success and "cambiada" in at.success[0].value
    login(logout(at), "Ana", "otra-contraseña-9")
    assert at.session_state["recruiter"] == "ana@sazon.test"


@table("old,new,again,message", [
    ("mala-contraseña-1", "otra-contraseña-9", None, "actual no es correcta"),
    (PASSWORD, "otra-contraseña-9", "distinta-contraseña-9", "no coinciden"), (PASSWORD, "corta", None, "al menos 8")])
def test_a_password_change_that_is_wrong_is_refused_and_nothing_changes(db, old, new, again, message):
    at = change_password(signed_in("Ana"), old, new, again)
    assert at.error and message in at.error[0].value
    assert db.verify_recruiter("ana@sazon.test", PASSWORD, NOW) is not None


# --- the hiring manager (from .env) creates and deletes recruiters -------------------------------------------------

def as_manager(monkeypatch):
    set_manager(monkeypatch)
    at = login_manager(fresh())
    assert not at.exception, at.exception
    return at


def open_recruiters(at):
    at.switch_page("views/recruiters.py").run()
    assert not at.exception, at.exception
    return at


def test_the_manager_signs_in_from_the_environment_and_sees_the_recruiters_page(db, monkeypatch):
    at = as_manager(monkeypatch)
    assert at.session_state["role"] == "manager" and at.session_state["recruiter"] == MANAGER_EMAIL
    assert not at.sidebar.expander or "contraseña" not in " ".join(str(e.label) for e in at.sidebar.expander).lower()
    assert [r["Correo"] for r in open_recruiters(at).dataframe[0].value.to_dict("records")] == ["ana@sazon.test", MANAGER_EMAIL, "luis@sazon.test"]  # the manager takes calls too


def test_a_recruiter_does_not_get_the_recruiters_page(db, monkeypatch):
    set_manager(monkeypatch)
    at = signed_in("Ana")
    assert at.session_state["role"] == "recruiter"
    with pytest.raises(ValueError):
        at.switch_page("views/recruiters.py")


def create(at, email="marta@sazon.test", name="Marta Gil", country="MX", password=PASSWORD, again=None):
    at.text_input(key="rec_email").set_value(email)
    at.text_input(key="rec_name").set_value(name)
    at.selectbox(key="rec_country").select(country)
    at.text_input(key="rec_password").set_value(password)
    at.text_input(key="rec_password_again").set_value(password if again is None else again)
    at.form_submit_button(key="rec_create").click().run()
    assert not at.exception, at.exception
    return at


def test_the_manager_creates_a_recruiter_who_can_then_sign_in_and_it_is_logged(db, monkeypatch):
    at = create(open_recruiters(as_manager(monkeypatch)))
    assert any("Marta Gil" in str(s.value) for s in at.success)
    entry = [e for e in db.admin_log() if e.action == "recruiter_created"][-1]
    assert (entry.actor, entry.detail) == (MANAGER_EMAIL, "marta@sazon.test (MX)")
    who = db.get_recruiter("marta@sazon.test")
    assert (who.name, who.country) == ("Marta Gil", "MX")
    assert signed_in("Marta").session_state["recruiter"] == "marta@sazon.test"


@table("fields,message", [
    (dict(email="ana@sazon.test"), "Ya hay un reclutador"), (dict(email="no-es-un-correo"), "correo válido"),
    (dict(name=" "), "nombre del reclutador"), (dict(password="corta"), "al menos 8"),
    (dict(again="otra-distinta-123"), "no coinciden")])
def test_a_recruiter_that_is_wrong_is_refused_and_nothing_is_created(db, monkeypatch, fields, message):
    at = create(open_recruiters(as_manager(monkeypatch)), **fields)
    assert at.error and message in at.error[0].value
    assert [r.email for r in db.recruiters()] == ["ana@sazon.test", MANAGER_EMAIL, "luis@sazon.test"]


def test_the_manager_takes_calls_so_they_have_hours_but_cannot_be_deleted_or_reset(db, monkeypatch):
    at = as_manager(monkeypatch)
    assert (db.get_recruiter(MANAGER_EMAIL).name, db.get_recruiter(MANAGER_EMAIL).country) == ("Hiring manager", "ES")
    at.switch_page("views/slots.py").run()
    assert any(MANAGER_EMAIL in label for label in at.selectbox(key="avail_who").options)  # their week can be edited
    open_recruiters(at)
    assert MANAGER_EMAIL in str(at.dataframe[0].value)
    for key in ("delete_who", "reset_who"):  # the password is in .env, and removing the manager would remove their calls
        assert not any(MANAGER_EMAIL in label for label in at.selectbox(key=key).options), key


def test_the_manager_deletes_a_recruiter_only_after_ticking_the_box(db, monkeypatch):
    at = open_recruiters(as_manager(monkeypatch))
    at.selectbox(key="delete_who").select("luis@sazon.test")
    at.button(key="delete_submit").click().run()
    assert at.error and db.get_recruiter("luis@sazon.test") is not None
    at.checkbox(key="delete_sure").check().run()
    at.button(key="delete_submit").click().run()
    assert db.get_recruiter("luis@sazon.test") is None and db.verify_recruiter("luis@sazon.test", PASSWORD, NOW) is None
    assert [e.action for e in db.admin_log()][-1] == "recruiter_removed"


def test_the_manager_resets_a_forgotten_password(db, monkeypatch):
    at = open_recruiters(as_manager(monkeypatch))
    at.selectbox(key="reset_who").select("ana@sazon.test")
    at.text_input(key="reset_password").set_value("restablecida-contraseña-3")
    at.form_submit_button(key="reset_submit").click().run()
    assert at.success and db.verify_recruiter("ana@sazon.test", "restablecida-contraseña-3", NOW)
    assert db.verify_recruiter("ana@sazon.test", PASSWORD, NOW) is None


# --- the applications switch ------------------------------------------------------------------------------------

def test_a_recruiter_can_close_and_reopen_applications_and_it_is_logged(db):
    at = signed_in("Ana")
    assert db.accepting_applications() is True
    at.sidebar.button(key="toggle_applications").click().run()
    assert db.accepting_applications() is False and any("CERRADAS" in str(c.value) for c in at.sidebar.caption)
    at.sidebar.button(key="toggle_applications").click().run()
    assert db.accepting_applications() is True
    assert [(e.actor, e.action) for e in db.admin_log() if e.action.startswith("applications")] == [
        ("recruiter:ana@sazon.test", "applications_closed"), ("recruiter:ana@sazon.test", "applications_opened")]


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
    assert entry.actor == "recruiter:ana@sazon.test" and "reason=request" in entry.detail and "Juan" not in entry.detail
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

def test_a_status_saved_for_one_candidate_does_not_carry_over_to_the_next(db):
    candidate(db, "c1", "Juan Pérez")
    candidate(db, "c2", "María García")
    at = signed_in()
    at.selectbox(key="candidate").select("c1").run()
    at.selectbox(key="new_status").select("hired")
    at.form_submit_button(key="save_status").click().run()
    assert db.recruiter("c1").status == RecruiterStatus.HIRED
    at.selectbox(key="candidate").select("c2").run()
    assert at.selectbox(key="new_status").value == "qualified"  # c2's own Estado, not c1's
    at.form_submit_button(key="save_status").click().run()  # saving without touching anything keeps it automatic
    assert db.recruiter("c2").status == RecruiterStatus.NEW


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
    assert at.text_input(key="f_search").value == "" and at.session_state["recruiter"] == "luis@sazon.test"
    assert at.selectbox(key="candidate").value is None


def test_deleting_a_recruiter_moves_or_releases_their_future_calls_and_says_how_many(db, monkeypatch):
    for name in ("Ana", "Luis"):
        db.reset_weekly(f"{name.lower()}@sazon.test", MANAGER_EMAIL, NOW)  # the default week: there are times to give
    for cid in ("c1", "c2"):
        candidate(db, cid, f"Persona {cid}")
    day = min(db.free_days("ES", NOW.date(), NOW.astimezone()))
    first = db.free_slots_on("ES", day, NOW.astimezone())[0]
    book_as_candidate(db, first.id, "c1")  # Ana
    book_as_candidate(db, first.id, "c2")  # Luis: both have a call at the same minute
    at = as_manager(monkeypatch)
    db.set_weekly(MANAGER_EMAIL, [], MANAGER_EMAIL, NOW)  # the manager takes calls too; here they are not free then
    open_recruiters(at)
    at.selectbox(key="delete_who").select("ana@sazon.test").run()
    assert any("Llamadas reservadas por delante: 1" in str(c.value) for c in at.caption)  # what leaving would affect
    at.checkbox(key="delete_sure").check().run()
    at.button(key="delete_submit").click().run()
    assert db.get_recruiter("ana@sazon.test") is None and not at.exception, at.exception
    assert db.booking_of("c1") is None and db.booking_of("c2") is not None  # Luis is busy then too: c1 is released, c2 is untouched
    assert "ya no está disponible" in db.outbox_pending("c1")[0].text and db.outbox_pending("c2") == []
    assert any("liberaron" in str(s.value) for s in at.success)
