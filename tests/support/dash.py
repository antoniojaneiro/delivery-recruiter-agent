"""Helpers shared by the dashboard tests: recruiters in the database, the hiring manager from the environment, and the real
sign-in by email and password."""
import os
from datetime import datetime, timedelta

from sazon.client import SAZON_CALENDAR
from screener.store import Store

PASSWORD = "contraseña-segura-1"
MANAGER_EMAIL = "jefa@sazon.test"
MANAGER_PASSWORD = "manager-password-1"


def email_of(name: str) -> str:
    return f"{name.lower()}@sazon.test"


def seed_accounts(path=None, *names, country="ES", available=False):
    """Creates recruiters (default Ana and Luis) in the database named by SAZON_DB, which a test sets first. They start
    with an empty week, so a test that adds call times by hand sees only those; `available=True` keeps the default
    week. The first argument is only kept so older calls read the same."""
    store = Store(os.environ["SAZON_DB"], calendar=SAZON_CALENDAR)
    for name in names or ("Ana", "Luis"):
        store.add_recruiter(email_of(name), name, country, PASSWORD, MANAGER_EMAIL, datetime(2026, 10, 1))
        if not available:
            store.set_weekly(email_of(name), [], MANAGER_EMAIL, datetime(2026, 10, 1))


def set_manager(monkeypatch):
    """The hiring manager of these tests, as the dashboard reads them from the environment."""
    monkeypatch.setenv("HIRING_MANAGER_EMAIL", MANAGER_EMAIL)
    monkeypatch.setenv("HIRING_MANAGER_PASSWORD", MANAGER_PASSWORD)


def login(at, name="Ana", password=PASSWORD):
    at.text_input(key="login_email").set_value(email_of(name))
    at.text_input(key="login_password").set_value(password)
    at.form_submit_button(key="login_submit").click().run()
    return at


def login_manager(at):
    at.text_input(key="login_email").set_value(MANAGER_EMAIL)
    at.text_input(key="login_password").set_value(MANAGER_PASSWORD)
    at.form_submit_button(key="login_submit").click().run()
    return at


def logout(at):
    at.sidebar.button(key="logout").click().run()
    return at


def book_as_candidate(store, slot_id, candidate_id):
    """Books a time the way the candidate's chat does, two days before it (a candidate only books from tomorrow, up to four
    weeks ahead, so the test's fixed or far dates are reached by moving `now`, not by changing the rule)."""
    slot = store.slot(slot_id)
    return store.book_slot(slot_id, candidate_id, (slot.starts_at - timedelta(days=2)).astimezone())
