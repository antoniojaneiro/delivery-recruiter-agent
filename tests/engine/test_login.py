"""D80: one sign-in for the dashboard. The hiring manager's email and password come from the environment (never stored
in the database); everyone else is a recruiter the manager created. A wrong password is counted the same for both."""
from datetime import datetime

import pytest

from tests.support.tables import table

from screener.login import Identity, ensure_manager_takes_calls, sign_in
from screener.recruiters import TooManyAttempts
from screener.store import Store
from sazon.client import SAZON_CALENDAR

NOW = datetime(2026, 10, 28, 10, 0)
MANAGER = ("Boss@Sazon.test", "manager-password-1")
PASSWORD = "contraseña-segura-1"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    s.add_recruiter("ana@sazon.test", "Ana Ruiz", "ES", PASSWORD, "boss@sazon.test", NOW)
    return s


def test_the_hiring_manager_signs_in_with_the_email_and_password_from_the_environment(store):
    who = sign_in(store, "boss@sazon.test", "manager-password-1", MANAGER, NOW)
    assert who == Identity("boss@sazon.test", "Hiring manager", "manager", None)
    assert sign_in(store, " BOSS@sazon.test ", "manager-password-1", MANAGER, NOW).role == "manager"


def test_a_recruiter_signs_in_as_a_recruiter_with_their_country(store):
    who = sign_in(store, "ana@sazon.test", PASSWORD, MANAGER, NOW)
    assert (who.email, who.name, who.role, who.country) == ("ana@sazon.test", "Ana Ruiz", "recruiter", "ES")


@table("email,password", [
    ("boss@sazon.test", "wrong"), ("boss@sazon.test", ""), ("ana@sazon.test", "wrong"), ("nobody@sazon.test", PASSWORD),
    ("", ""), ("ana@sazon.test", "manager-password-1")])
def test_a_wrong_email_or_password_is_not_signed_in(store, email, password):
    assert sign_in(store, email, password, MANAGER, NOW) is None


def test_without_a_manager_in_the_environment_only_recruiters_can_sign_in(store):
    assert sign_in(store, "boss@sazon.test", "manager-password-1", None, NOW) is None
    assert sign_in(store, "ana@sazon.test", PASSWORD, None, NOW).role == "recruiter"


def test_five_wrong_manager_passwords_lock_the_manager_too(store):
    for _ in range(5):
        assert sign_in(store, "boss@sazon.test", "wrong", MANAGER, NOW) is None
    with pytest.raises(TooManyAttempts):
        sign_in(store, "boss@sazon.test", "manager-password-1", MANAGER, NOW)


def test_the_manager_is_not_a_recruiter_and_has_no_stored_password(store, tmp_path):
    assert store.get_recruiter("boss@sazon.test") is None
    raw = b"".join(p.read_bytes() for p in tmp_path.glob("s.db*"))
    assert b"manager-password-1" not in raw


def test_an_unconfigured_manager_with_an_empty_password_never_matches(store):
    assert sign_in(store, "boss@sazon.test", "", ("boss@sazon.test", ""), NOW) is None


def test_the_hiring_manager_takes_calls_with_the_default_week_and_signs_in_only_with_the_environment_password(store):
    ensure_manager_takes_calls(store, MANAGER, "ES", NOW)
    ensure_manager_takes_calls(store, MANAGER, "ES", NOW)  # a second time changes nothing
    [row] = [r for r in store.recruiters() if r.email == "boss@sazon.test"]
    assert (row.name, row.country) == ("Hiring manager", "ES")
    assert any(s.recruiter == "boss@sazon.test" and s.candidate_id is None for s in store.slots(NOW.astimezone()))  # their own times
    who = sign_in(store, "boss@sazon.test", "manager-password-1", MANAGER, NOW)
    assert (who.role, who.country) == ("manager", "ES")
    assert sign_in(store, "boss@sazon.test", "anything-else-1", MANAGER, NOW) is None
    assert sign_in(store, "boss@sazon.test", "manager-password-1", None, NOW) is None  # no manager in the environment: no way in


@table("manager,country,rows", [(None, "ES", 1), (MANAGER, "MX", 2)])
def test_the_manager_row_is_made_only_with_a_manager_and_in_the_chosen_country(store, manager, country, rows):
    ensure_manager_takes_calls(store, manager, country, NOW)
    assert len(store.recruiters()) == rows
    assert not manager or store.get_recruiter("boss@sazon.test").country == country
