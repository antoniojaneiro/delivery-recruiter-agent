"""The two apps point at each other: the chat to the dashboard and the dashboard to the chat. The addresses default to
the ports demo_launch.py uses and can be set with SAZON_CHAT_URL and SAZON_DASHBOARD_URL."""
import pytest
from streamlit.testing.v1 import AppTest

from sazon import config
from screener.store import Store
from tests.support.dash import login, seed_accounts
from tests.support.fakes import ScriptedLLM
from tests.support.paths import CHAT_APP, DASHBOARD


def test_the_addresses_default_to_the_ports_of_the_launcher(monkeypatch):
    monkeypatch.delenv("SAZON_CHAT_URL", raising=False)
    monkeypatch.delenv("SAZON_DASHBOARD_URL", raising=False)
    assert config.chat_url() == "http://localhost:8501" and config.dashboard_url() == "http://localhost:8502"


def test_the_addresses_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("SAZON_CHAT_URL", "https://chat.example.test")
    monkeypatch.setenv("SAZON_DASHBOARD_URL", "https://panel.example.test")
    assert (config.chat_url(), config.dashboard_url()) == ("https://chat.example.test", "https://panel.example.test")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "real.db"))
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "recruiters.json"))
    monkeypatch.setenv("SAZON_CHAT_URL", "http://chat.test")
    monkeypatch.setenv("SAZON_DASHBOARD_URL", "http://panel.test")
    monkeypatch.setattr("screener.gemini.from_env", lambda: ScriptedLLM())
    seed_accounts(tmp_path / "recruiters.json")


@pytest.mark.parametrize("language,label", [("es", "Abrir el panel de reclutadores"), ("en", "Open the recruiters' dashboard")])
def test_the_chat_links_to_the_dashboard_in_the_page_language(env, language, label):
    at = AppTest.from_file(str(CHAT_APP), default_timeout=15)
    at.session_state["ui_language"] = language
    at.run()
    links = at.sidebar.link_button
    assert [(b.value, b.url) for b in links] == [(label, "http://panel.test")]


@pytest.mark.parametrize("language,label", [("es", "Probar el chat de candidatos"), ("en", "Try the candidate chat")])
def test_the_dashboard_links_to_the_chat_once_signed_in(env, language, label):
    at = AppTest.from_file(str(DASHBOARD), default_timeout=15)
    at.session_state["ui_language"] = language
    at.run()
    assert not at.sidebar.link_button  # nothing on the login page
    login(at)
    assert [(b.value, b.url) for b in at.sidebar.link_button] == [(label, "http://chat.test")]
