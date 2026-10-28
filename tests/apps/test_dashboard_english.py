"""D66: the dashboard in English. Every page renders without an error and shows none of the Spanish page text."""
from datetime import date, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.support.paths import DASHBOARD
from sazon.client import SAZON_CALENDAR, SAZON_CLIENT
from sazon.spec import SAZON
from screener import session
from screener.screening import Screening
from screener.store import Store
from tests.support.dash import login, logout, seed_accounts

APP = str(DASHBOARD)
NOW = datetime(2026, 10, 25, 10, 0)
TODAY = date(2026, 10, 25)
SPANISH = ["Candidatos", "Resumen", "Cualificad", "Licencia", "Horarios", "Embudo", "Guardar", "Auditor", "Conversaci",
           "Contrase", "Entrar", "Nuevo", "Borrar", "Sesi", "Reclutador", "Etapa", "Motivo", "Falta:", "Llamada"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "sazon.db"
    monkeypatch.setenv("SAZON_DB", str(path))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    seed_accounts(tmp_path / "recruiters.json")
    store = Store(path, calendar=SAZON_CALENDAR)
    screening = Screening(SAZON_CLIENT.areas, SAZON)
    screening.record_consent(True)
    for field, value in {"name": "Juan Pérez", "experience": (2, ["glovo"]), "availability": ["full_time"],
                         "schedule": "morning", "start_date": date(2026, 11, 1), "city": "Madrid",
                         "license": True}.items():
        screening.submit(field, value, TODAY)
    session.commit(store, "c1", screening, NOW, messages=[("agent", "Hola"), ("candidate", "sí")])
    return store


def on_english(page=None):
    at = AppTest.from_file(APP, default_timeout=10)
    at.session_state["ui_language"] = "en"
    at.run()
    return at


def shown_text(at) -> str:
    parts = []
    for kind in ("title", "header", "subheader", "caption", "markdown", "text", "info", "warning", "error", "success"):
        parts += [str(e.value) for e in getattr(at, kind)]
    for kind in ("button", "text_input", "selectbox", "multiselect", "checkbox", "text_area"):
        parts += [str(e.label) for e in getattr(at, kind)]
    parts += [str(m.label) for m in at.metric] + [str(t.label) for t in at.tabs]
    return " | ".join(parts)


def assert_english(at):
    assert not at.exception, at.exception
    text = shown_text(at)
    assert not [word for word in SPANISH if word in text], (text,)


def test_the_login_screen_is_in_english_and_the_switch_is_there(db):
    at = on_english()
    assert at.title[0].value == "Grupo Sazón · Recruiting"
    assert at.text_input(key="login_name").label == "Name" and at.text_input(key="login_password").label == "Password"
    assert at.segmented_control(key="ui_language").value == "en"
    assert_english(at)


def test_choosing_a_language_on_the_login_screen_changes_the_screen(db):
    at = AppTest.from_file(APP, default_timeout=10).run()
    assert at.title[0].value == "Grupo Sazón · Reclutamiento"
    at.segmented_control(key="ui_language").set_value("en").run()
    assert at.title[0].value == "Grupo Sazón · Recruiting"


def test_the_candidates_page_and_the_card_are_in_english(db):
    at = on_english()
    login(at)
    assert_english(at)
    assert at.title[0].value == "Candidates"
    assert {m.label for m in at.metric} >= {"Candidates", "Qualified to contact", "Rejections to review"}
    at.selectbox(key="candidate").select("c1").run()
    assert_english(at)
    card = next(e.value for e in at.text if "Experience:" in str(e.value))
    assert card.splitlines()[0] == "Juan Pérez · Madrid · Qualified" and "License: yes" in card.splitlines()
    assert list(at.dataframe[0].value.columns)[:3] == ["Id", "Name", "City"]


def test_the_stored_card_stays_spanish_whatever_the_screen_language(db):
    at = on_english()
    login(at)
    at.selectbox(key="candidate").select("c1").run()
    assert db.get("c1").summary.splitlines()[0] == "Juan Pérez · Madrid · Cualificado"


def test_the_call_times_and_the_funnel_pages_are_in_english(db):
    at = on_english()
    login(at)
    at.switch_page("views/slots.py").run()
    assert_english(at)
    assert at.title[0].value == "Call calendar"
    at.switch_page("views/funnel.py").run()
    assert_english(at)
    assert at.title[0].value == "Candidate funnel"
    assert {m.label for m in at.metric} >= {"Started", "Gave consent", "Qualified"}


def test_the_language_survives_signing_out(db):
    at = on_english()
    login(at)
    logout(at)
    assert at.title[0].value == "Grupo Sazón · Recruiting"


def test_spanish_is_still_the_default(db):
    at = AppTest.from_file(APP, default_timeout=10).run()
    login(at)
    assert at.title[0].value == "Candidatos"


@pytest.mark.parametrize("language,expected", [("es", "Elegir opciones"), ("en", "Choose options")])
def test_the_filter_dropdowns_say_their_placeholder_in_the_page_language(db, language, expected):
    """Streamlit's own default placeholder is English whatever the app's language switch says."""
    at = AppTest.from_file(APP, default_timeout=20)
    at.session_state["ui_language"] = language
    at.run()
    login(at)
    assert not at.exception, at.exception
    assert {at.multiselect(key="f_outcome").proto.placeholder, at.multiselect(key="f_status").proto.placeholder} == {expected}
