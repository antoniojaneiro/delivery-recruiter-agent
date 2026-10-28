"""Test-wide setup."""
import pytest

from screener import recruiters


@pytest.fixture(autouse=True)
def _no_manager_unless_a_test_sets_one(monkeypatch):
    """The real .env is read by the dashboard; a test has no hiring manager unless it sets one."""
    monkeypatch.setenv("HIRING_MANAGER_EMAIL", "")
    monkeypatch.setenv("HIRING_MANAGER_PASSWORD", "")


@pytest.fixture(autouse=True, scope="session")
def _cheap_passwords():
    """Real passwords are hashed with a deliberately slow scrypt; the tests do not need that cost (a hash keeps the
    parameters it was made with, so the checks are the same)."""
    original = dict(recruiters.SCRYPT)
    recruiters.SCRYPT.update(n=2 ** 4)
    yield
    recruiters.SCRYPT.update(original)
