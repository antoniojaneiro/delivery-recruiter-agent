"""D80: one sign-in for the dashboard. The hiring manager's email and password come from the environment (never stored
in the database); everyone else is a recruiter the manager created. A wrong password is counted the same for both."""
from datetime import datetime

import pytest

from screener.login import Identity, sign_in
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


@pytest.mark.parametrize("email,password", [
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
