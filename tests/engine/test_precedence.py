"""D63: what the agent says first when several things wait is one plain function with a table of its own."""
from screener.directive import Directive, Kind
from screener.screening_precedence import Waiting, directive_for

CLOSE = Directive(Kind.CLOSE)
EVERYTHING = Waiting(is_open=True, rejection="license", rejection_subject="Leeds", area="Madrid",
                     change=("name", "x", "old", "new"), blocked_on="shift", next_field="town")


def said(waiting, unclear=None):
    return directive_for(waiting, unclear, CLOSE)


def test_a_closed_chat_only_closes_whatever_else_waits():
    assert said(EVERYTHING.__class__(**{**EVERYTHING.__dict__, "is_open": False})) is CLOSE


def test_the_order_is_rejection_then_area_then_change_then_blocked_then_unclear_then_the_next_question():
    w = EVERYTHING
    assert said(w).kind == Kind.CONFIRM_REJECTION and said(w).suggestion == "Leeds"
    w = Waiting(**{**w.__dict__, "rejection": None, "rejection_subject": None})
    assert said(w).kind == Kind.CONFIRM_AREA and said(w).suggestion == "Madrid"
    w = Waiting(**{**w.__dict__, "area": None})
    assert said(w).kind == Kind.CONFIRM_CHANGE and said(w).options == ["old", "new"] and said(w).field == "name"
    w = Waiting(**{**w.__dict__, "change": None})
    assert said(w).kind == Kind.BLOCKED and said(w).field == "shift"
    w = Waiting(**{**w.__dict__, "blocked_on": None})
    assert said(w, ("name", "need a surname")).kind == Kind.FOLLOW_UP
    assert said(w, ("name", "need a surname")).reason == "need a surname"
    assert said(w).kind == Kind.ASK and said(w).field == "town"
