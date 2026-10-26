"""Review round D61, last group: accounts file safety, login throttle, paths, length caps, .gitignore."""
import json
from datetime import date
from pathlib import Path

import pytest

from sazon import accounts, config
from sazon.screening import Screening
from sazon.validators import validate_name

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def path(tmp_path):
    return tmp_path / "recruiters.json"


def test_a_damaged_accounts_file_is_not_overwritten_by_add_or_remove(path):
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(accounts.DamagedAccounts):
        accounts.add_account(path, "Ana", "password123")
    with pytest.raises(accounts.DamagedAccounts):
        accounts.remove_account(path, "Ana")
    assert path.read_text(encoding="utf-8") == "{not json"


def test_a_missing_file_is_fine_for_the_first_account(path):
    accounts.add_account(path, "Ana", "password123")
    assert accounts.verify(path, "Ana", "password123") == "Ana"


def test_saving_leaves_no_temporary_file_behind(path):
    accounts.add_account(path, "Ana", "password123")
    assert [p.name for p in path.parent.iterdir()] == ["recruiters.json"]


def test_new_passwords_use_the_stronger_cost_and_old_hashes_still_verify(path):
    accounts.add_account(path, "Ana", "password123")
    assert json.loads(path.read_text(encoding="utf-8"))["ana"]["params"]["n"] == 2 ** 16
    data = json.loads(path.read_text(encoding="utf-8"))
    old = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
    salt = bytes(range(16))
    data["luis"] = {"name": "Luis", "algorithm": "scrypt", "params": old, "salt": salt.hex(),
                    "hash": accounts._hash("password123", salt, old).hex()}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert accounts.verify(path, "Luis", "password123") == "Luis"


def test_five_wrong_passwords_lock_the_name_for_ten_minutes_even_for_the_right_one(path):
    accounts.add_account(path, "Ana", "password123")
    accounts.reset_throttle()
    for _ in range(accounts.MAX_FAILURES):
        assert accounts.verify(path, "Ana", "wrong", now=100.0) is None
    with pytest.raises(accounts.TooManyAttempts):
        accounts.verify(path, "Ana", "password123", now=200.0)
    assert accounts.verify(path, "Ana", "password123", now=100.0 + accounts.LOCK_SECONDS + 1) == "Ana"


def test_a_success_clears_earlier_failures(path):
    accounts.add_account(path, "Ana", "password123")
    accounts.reset_throttle()
    for _ in range(accounts.MAX_FAILURES - 1):
        accounts.verify(path, "Ana", "wrong", now=1.0)
    assert accounts.verify(path, "Ana", "password123", now=2.0) == "Ana"
    for _ in range(accounts.MAX_FAILURES - 1):
        accounts.verify(path, "Ana", "wrong", now=3.0)
    assert accounts.verify(path, "Ana", "password123", now=4.0) == "Ana"


def test_paths_do_not_depend_on_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("SAZON_DB", raising=False)
    monkeypatch.delenv("SAZON_ACCOUNTS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.db_path().is_absolute() and config.db_path().is_relative_to(ROOT)
    assert accounts.accounts_path().is_absolute() and accounts.accounts_path().is_relative_to(ROOT)


def test_a_very_long_name_is_refused():
    assert not validate_name("Ana " + "a" * 200).ok


def test_a_very_long_outside_city_is_stored_cut_short():
    s = Screening(config.AREAS)
    s.record_consent(True)
    s.submit("city", "Springfield " * 100, date(2026, 10, 25))
    s.confirm_rejection(True)
    assert len(s.values["city"]) <= 80


def test_secrets_files_are_ignored_by_git():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert ".streamlit/secrets.toml" in lines and "recruiters.json" in lines
