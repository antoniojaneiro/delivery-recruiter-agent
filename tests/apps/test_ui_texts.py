"""D66: every word the dashboard shows lives in a text pack with one entry per language; the pages hold none."""
import ast
import re
from pathlib import Path

import pytest

from tests.support.paths import DASHBOARD, CHAT_APP, VIEWS
from screener.model import Language
from screener.ui_texts import UiPack, UiTextError

ES, EN = Language.ES, Language.EN
PAGES = [DASHBOARD, *sorted(VIEWS.glob("*.py")), CHAT_APP]


def test_a_text_missing_in_a_language_is_refused():
    with pytest.raises(UiTextError) as error:
        UiPack((ES, EN), {"a": {ES: "hola"}, "b": {ES: "x", EN: "y"}})
    assert "a" in str(error.value) and "en" in str(error.value)


def test_a_placeholder_that_differs_between_languages_is_refused():
    with pytest.raises(UiTextError) as error:
        UiPack((ES, EN), {"greeting": {ES: "Hola {name}", EN: "Hello {who}"}})
    assert "greeting" in str(error.value)


def test_a_text_is_filled_in_and_an_unknown_key_is_a_clear_error():
    pack = UiPack((ES, EN), {"hi": {ES: "Hola {name}", EN: "Hello {name}"}})
    assert pack.get("hi", EN, name="Ana") == "Hello Ana" and pack.get("hi", "es", name="Ana") == "Hola Ana"
    with pytest.raises(UiTextError):
        pack.get("nope", EN)


def literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Constant)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.value, node.lineno


ALLOWED = {"%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m", "%d/%m/%Y", "%H:%M"}  # a date or time format is not a word
CHART_FIELD = re.compile(r"^[a-z_]+:[QNOT]$")  # altair shorthand such as "count:Q"


def test_the_pages_hold_no_visible_text_only_keys_and_technical_names():
    """A visible text has a capital, a space or an accent; a key or option name is lowercase without spaces."""
    found = []
    for path in PAGES:
        for value, line in literals(path):
            if value in ALLOWED or CHART_FIELD.match(value) or not any(c.isalpha() for c in value):  # punctuation is not a word
                continue
            if value != value.lower() or " " in value or not value.isascii():
                found.append(f"{path.name}:{line}: {value[:40]!r}")
    assert found == []


# keys the pages pass around in a variable (a message kept in the session, shown after a rerun)
DYNAMIC_KEYS = {"erase.need_check", "erase.done", "chat.wait_nothing"}


def test_every_key_the_pages_ask_for_exists_in_the_pack():
    from sazon.ui_pack import PACK
    asked = set()
    for path in PAGES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("t", "tc") \
                    and node.args and isinstance(node.args[0], ast.Constant):
                asked.add(node.args[0].value)
    asked |= DYNAMIC_KEYS
    assert asked and asked <= set(PACK.texts), sorted(asked - set(PACK.texts))
