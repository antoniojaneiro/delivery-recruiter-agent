"""D80: the recruiters live in the database (email, name, country, a salted scrypt hash). Only the hiring manager, whose
email and password come from the environment, creates and deletes them. Sign-in is by email and password, five wrong
passwords lock an email for ten minutes (kept in the database, so a restart does not clear it), and a recruiter changes
their own password while the manager can reset it."""
from datetime import datetime

import pytest

from screener.recruiters import MIN_PASSWORD_LENGTH, TooManyAttempts
from screener.store import InputError, Store
from sazon.client import SAZON_CALENDAR

NOW = datetime(2026, 10, 28, 10, 0)
PASSWORD = "contraseña-segura-1"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)


def add(store, email="ana@sazon.test", name="Ana Ruiz", country="ES", password=PASSWORD):
    return store.add_recruiter(email, name, country, password, "boss@sazon.test", NOW)


def test_a_recruiter_is_created_with_email_name_country_and_listed(store):
    created = add(store)
    assert (created.email, created.name, created.country) == ("ana@sazon.test", "Ana Ruiz", "ES")
    add(store, "luis@sazon.test", "Luis Gómez", "MX")
    assert [(r.email, r.country) for r in store.recruiters()] == [("ana@sazon.test", "ES"), ("luis@sazon.test", "MX")]
    assert store.get_recruiter("ANA@Sazon.test").name == "Ana Ruiz"  # an email is not case sensitive


def test_the_password_is_never_stored_as_typed(store, tmp_path):
    add(store)
    store.checkpoint_for_tests() if hasattr(store, "checkpoint_for_tests") else None
    raw = b"".join(p.read_bytes() for p in tmp_path.glob("s.db*"))
    assert PASSWORD.encode() not in raw


@pytest.mark.parametrize("fields,code", [
    (dict(email="not-an-email"), "email_invalid"), (dict(email=""), "email_invalid"),
    (dict(name="  "), "name_missing"), (dict(country="FR"), "unknown_country"),
    (dict(password="short"), "password_short"), (dict(password=""), "password_short")])
def test_a_recruiter_that_cannot_be_created_says_why(store, fields, code):
    with pytest.raises(InputError) as refused:
        add(store, **fields)
    assert refused.value.code == code and store.recruiters() == []


def test_the_same_email_cannot_be_used_twice_in_any_case(store):
    add(store)
    with pytest.raises(InputError) as refused:
        add(store, "ANA@SAZON.TEST", "Another")
    assert refused.value.code == "exists" and len(store.recruiters()) == 1


def test_the_password_needs_a_minimum_length():
    assert MIN_PASSWORD_LENGTH == 8


def test_signing_in_returns_the_recruiter_for_the_right_password_only(store):
    add(store)
    assert store.verify_recruiter("ana@sazon.test", PASSWORD, NOW).name == "Ana Ruiz"
    assert store.verify_recruiter("ANA@sazon.test ", PASSWORD, NOW).email == "ana@sazon.test"
    assert store.verify_recruiter("ana@sazon.test", "wrong-password", NOW) is None
    assert store.verify_recruiter("nobody@sazon.test", PASSWORD, NOW) is None


def test_five_wrong_passwords_lock_the_email_for_ten_minutes_even_for_the_right_one(store):
    add(store)
    for _ in range(5):
        assert store.verify_recruiter("ana@sazon.test", "wrong-password", NOW) is None
    with pytest.raises(TooManyAttempts):
        store.verify_recruiter("ana@sazon.test", PASSWORD, NOW)
    later = datetime(2026, 10, 28, 10, 11)
    assert store.verify_recruiter("ana@sazon.test", PASSWORD, later).name == "Ana Ruiz"


def test_the_lockout_survives_a_restart_and_a_success_clears_the_failures(store, tmp_path):
    add(store)
    for _ in range(4):
        store.verify_recruiter("ana@sazon.test", "wrong-password", NOW)
    assert store.verify_recruiter("ana@sazon.test", PASSWORD, NOW)  # a success clears them
    for _ in range(5):
        store.verify_recruiter("ana@sazon.test", "wrong-password", NOW)
    again = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)  # a restart
    with pytest.raises(TooManyAttempts):
        again.verify_recruiter("ana@sazon.test", PASSWORD, NOW)


def test_a_recruiter_changes_their_own_password_only_with_the_old_one(store):
    add(store)
    with pytest.raises(InputError) as refused:
        store.change_password("ana@sazon.test", "wrong-password", "a-new-password-1", NOW)
    assert refused.value.code == "wrong_password"
    store.change_password("ana@sazon.test", PASSWORD, "a-new-password-1", NOW)
    assert store.verify_recruiter("ana@sazon.test", PASSWORD, NOW) is None
    assert store.verify_recruiter("ana@sazon.test", "a-new-password-1", NOW)
    with pytest.raises(InputError):
        store.change_password("ana@sazon.test", "a-new-password-1", "short", NOW)


def test_the_manager_resets_a_password_and_it_is_logged(store):
    add(store)
    store.reset_password("ana@sazon.test", "reset-by-manager-1", "boss@sazon.test", NOW)
    assert store.verify_recruiter("ana@sazon.test", "reset-by-manager-1", NOW)
    assert "password_reset" in [e.action for e in store.admin_log()]
    with pytest.raises(LookupError):
        store.reset_password("nobody@sazon.test", "reset-by-manager-1", "boss@sazon.test", NOW)


def test_deleting_a_recruiter_removes_the_sign_in_and_is_logged(store):
    add(store)
    assert store.remove_recruiter("ana@sazon.test", "boss@sazon.test", NOW) is True
    assert store.recruiters() == [] and store.verify_recruiter("ana@sazon.test", PASSWORD, NOW) is None
    assert store.remove_recruiter("ana@sazon.test", "boss@sazon.test", NOW) is False
    assert [e.action for e in store.admin_log()][-2:] == ["recruiter_created", "recruiter_removed"]


def test_creating_a_recruiter_is_logged_with_who_did_it_and_never_the_password(store):
    add(store)
    entry = store.admin_log()[-1]
    assert entry.action == "recruiter_created" and entry.actor == "boss@sazon.test"
    assert PASSWORD not in entry.detail and "ana@sazon.test" in entry.detail
