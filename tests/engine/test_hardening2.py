"""Review round D61, last group: paths, length caps, .gitignore. (The sign-in lockout moved with the recruiters into the
database, D80: see test_recruiters.py.)"""
from datetime import date

from sazon.areas import AREAS
from tests.support.paths import ROOT
from sazon.spec import SAZON
from sazon import config
from screener.screening import Screening
from screener.validators import validate_name


def test_paths_do_not_depend_on_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("SAZON_DB", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.db_path().is_absolute() and config.db_path().is_relative_to(ROOT)


def test_a_very_long_name_is_refused():
    assert not validate_name("Ana " + "a" * 200).ok


def test_a_very_long_outside_city_is_stored_cut_short():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.submit("city", "Springfield " * 100, date(2026, 10, 25))
    s.confirm_rejection(True)
    assert len(s.values["city"]) <= 80


def test_secrets_files_are_ignored_by_git():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert ".streamlit/secrets.toml" in lines and ".env" in lines
