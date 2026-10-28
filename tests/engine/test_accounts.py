"""D57: one account per recruiter; passwords only as salted hashes; no accounts means no access."""
import json

import pytest

from screener import accounts

from sazon import accounts as sazon_accounts

PASSWORD = "contraseña-segura-1"


@pytest.fixture
def path(tmp_path):
    return tmp_path / "recruiters.json"


def test_a_recruiter_can_sign_in_with_the_right_password(path):
    accounts.add_account(path, "Ana", PASSWORD)
    assert accounts.verify(path, "Ana", PASSWORD) == "Ana"


@pytest.mark.parametrize("name", ["ana", "ANA", "  Ana  "])
def test_the_name_is_matched_ignoring_case_and_spaces_and_returns_the_name_as_registered(path, name):
    accounts.add_account(path, "Ana", PASSWORD)
    assert accounts.verify(path, name, PASSWORD) == "Ana"


@pytest.mark.parametrize("name,password", [("Ana", "otra-contraseña-1"), ("Ana", ""), ("Luis", PASSWORD), ("", PASSWORD)])
def test_a_wrong_password_or_an_unknown_name_is_refused_the_same_way(path, name, password):
    accounts.add_account(path, "Ana", PASSWORD)
    assert accounts.verify(path, name, password) is None


def test_the_password_is_never_stored_and_each_account_has_its_own_salt(path):
    accounts.add_account(path, "Ana", PASSWORD)
    accounts.add_account(path, "Luis", PASSWORD)
    text = path.read_text(encoding="utf-8")
    assert PASSWORD not in text
    data = json.loads(text)
    assert data["ana"]["salt"] != data["luis"]["salt"] and data["ana"]["hash"] != data["luis"]["hash"]
    assert data["ana"]["algorithm"] == "scrypt"


def test_bad_accounts_are_refused(path):
    with pytest.raises(ValueError):
        accounts.add_account(path, "  ", PASSWORD)
    with pytest.raises(ValueError):
        accounts.add_account(path, "Ana", "corta")
    accounts.add_account(path, "Ana", PASSWORD)
    with pytest.raises(ValueError):
        accounts.add_account(path, "ana", PASSWORD)


def test_a_password_can_be_reset_and_an_account_removed(path):
    accounts.add_account(path, "Ana", PASSWORD)
    accounts.add_account(path, "Ana", "nueva-contraseña-2", replace=True)
    assert accounts.verify(path, "Ana", PASSWORD) is None
    assert accounts.verify(path, "Ana", "nueva-contraseña-2") == "Ana"
    assert accounts.remove_account(path, "ana") is True and accounts.remove_account(path, "ana") is False
    assert accounts.verify(path, "Ana", "nueva-contraseña-2") is None


def test_with_no_accounts_file_nobody_gets_in(path):
    assert accounts.has_accounts(path) is False
    assert accounts.verify(path, "Ana", PASSWORD) is None


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"ana": "x"}', '{"ana": {"salt": "zz"}}', "null"])
def test_a_damaged_accounts_file_means_nobody_gets_in_and_nothing_crashes(path, content):
    path.write_text(content, encoding="utf-8")
    assert accounts.verify(path, "ana", PASSWORD) is None
    assert accounts.has_accounts(path) is False


def test_listing_gives_the_registered_names(path):
    accounts.add_account(path, "Luis", PASSWORD)
    accounts.add_account(path, "Ana", PASSWORD)
    assert accounts.list_names(path) == ["Ana", "Luis"]


def test_the_default_path_comes_from_the_environment_or_the_data_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("SAZON_ACCOUNTS", str(tmp_path / "x.json"))
    assert sazon_accounts.accounts_path() == tmp_path / "x.json"
    monkeypatch.delenv("SAZON_ACCOUNTS")
    assert sazon_accounts.accounts_path().name == "recruiters.json" and sazon_accounts.accounts_path().parent.name == "data"


def test_the_command_adds_lists_and_removes(path, monkeypatch, capsys):
    monkeypatch.setenv("SAZON_ACCOUNTS", str(path))
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    sazon_accounts.main(["add", "Ana"])
    sazon_accounts.main(["list"])
    assert "Ana" in capsys.readouterr().out
    assert accounts.verify(path, "Ana", PASSWORD) == "Ana"
    sazon_accounts.main(["remove", "Ana"])
    assert accounts.has_accounts(path) is False


def test_the_command_refuses_passwords_that_do_not_match(path, monkeypatch):
    monkeypatch.setenv("SAZON_ACCOUNTS", str(path))
    answers = iter([PASSWORD, "otra-distinta-9"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    with pytest.raises(SystemExit):
        sazon_accounts.main(["add", "Ana"])
    assert accounts.has_accounts(path) is False


# --- creating accounts from the dashboard ------------------------------------------------------------------------

def test_the_first_account_can_be_created_only_while_there_are_no_accounts(path):
    assert accounts.create_first(path, "  Ana  ", PASSWORD) == "Ana"
    with pytest.raises(accounts.AccountError) as error:
        accounts.create_first(path, "Intruso", PASSWORD)
    assert error.value.code == "not_first" and accounts.list_names(path) == ["Ana"]


@pytest.mark.parametrize("name,password,code", [("", PASSWORD, "name_required"), ("   ", PASSWORD, "name_required"),
                                                ("Ana", "corta", "password_short"), ("Ana", "", "password_short")])
def test_an_account_with_no_name_or_a_short_password_is_refused_with_a_code(path, name, password, code):
    with pytest.raises(accounts.AccountError) as error:
        accounts.add_account(path, name, password)
    assert error.value.code == code and not accounts.has_accounts(path)


def test_a_second_account_with_the_same_name_is_refused_with_a_code(path):
    accounts.add_account(path, "Ana", PASSWORD)
    with pytest.raises(accounts.AccountError) as error:
        accounts.add_account(path, "ana", PASSWORD)
    assert error.value.code == "exists"


def test_add_account_returns_the_name_as_stored_and_account_errors_are_still_value_errors(path):
    assert accounts.add_account(path, "  Luis   Gil ", PASSWORD) == "Luis Gil"
    with pytest.raises(ValueError):
        accounts.add_account(path, "", PASSWORD)


def test_the_store_can_log_an_admin_action_with_its_actor(tmp_path):
    from datetime import datetime
    from screener.store import Store
    store = Store(tmp_path / "s.db")
    store.log_admin("recruiter:Ana", "account_created", "Luis", datetime(2026, 10, 28, 10, 0))
    [entry] = store.admin_log()
    assert (entry.actor, entry.action, entry.detail) == ("recruiter:Ana", "account_created", "Luis")
