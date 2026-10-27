"""D70: a Directive is what the engine decided to say. It lives apart from the wording, and its notices are names."""
import pytest

from screener.directive import NOTICE_NAMES, Directive, Kind


def test_a_directive_has_no_notices_until_it_is_given_some():
    assert Directive(Kind.ASK, field="name").notices == ()
    assert Directive(Kind.ASK, field="name", notices=("human", "pay")).notices == ("human", "pay")


def test_a_notice_name_that_does_not_exist_is_refused_when_the_directive_is_built():
    with pytest.raises(ValueError) as error:
        Directive(Kind.ASK, field="name", notices=("humna",))
    assert "humna" in str(error.value)
    assert set(NOTICE_NAMES) == {"human", "pay", "changed", "kept", "offtopic"}


def test_deciding_does_not_depend_on_the_wording_module():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "screener"
    for name in ("screening.py", "screening_precedence.py", "slot_flow.py", "directive.py"):
        wording_helpers = {"consent_text_hash", "slot_label", "slot_cancelled_message"}  # texts, not decisions
        for node in ast.walk(ast.parse((root / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "screener.phrasing":
                assert {a.name for a in node.names} <= wording_helpers, (name, [a.name for a in node.names])
