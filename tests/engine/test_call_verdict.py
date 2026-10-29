"""D94: who may be given a call is two questions, each answered in one place with its reason. A recruiter may book or move a
call for a candidate shown as Qualified or Interview scheduled (they may already hold one); a candidate may choose a time now
only when nobody has closed their case, the client books calls and they hold none yet. Pure over a record, so the calendar page
can ask it of thousands of records without a store call each."""
from screener.model import RecruiterStatus as S
from screener.recruiter_rules import Verdict, may_choose, may_schedule
from tests.support.tables import table


class Shown:
    def __init__(self, stage):
        self.stage = stage


@table("stage,allowed,reason", [
    (S.QUALIFIED, True, None), (S.INTERVIEW_SCHEDULED, True, None),
    (S.CONTACTED, False, "not_qualified"), (S.NEW, False, "not_qualified"),
    (S.HIRED, False, "closed"), (S.REJECTED, False, "closed"), (S.UNREACHABLE, False, "closed"),
])
def test_a_recruiter_may_book_or_move_a_call_for_a_qualified_candidate_who_may_already_hold_one(stage, allowed, reason):
    assert may_schedule(Shown(stage)) == Verdict(allowed, reason)


@table("stage,books_calls,holds_call,allowed,reason", [
    (S.QUALIFIED, True, False, True, None),
    (S.QUALIFIED, True, True, False, "already_booked"),
    (S.INTERVIEW_SCHEDULED, True, True, False, "already_booked"),
    (S.QUALIFIED, False, False, False, "no_calendar"),          # a client that books no calls: whatever the stage
    (S.CONTACTED, True, False, False, "not_qualified"),
    (S.HIRED, True, False, False, "closed"),
    (S.REJECTED, True, True, False, "closed"),                  # closed wins over a call they still hold
    (S.CONTACTED, False, False, False, "no_calendar"),
])
def test_a_candidate_may_choose_a_time_only_when_nobody_closed_their_case_and_they_hold_none(stage, books_calls, holds_call, allowed, reason):
    assert may_choose(Shown(stage), books_calls=books_calls, holds_call=holds_call) == Verdict(allowed, reason)


def test_no_record_is_never_allowed():
    assert may_choose(None, books_calls=True, holds_call=False) == Verdict(False, "unknown")
    assert may_schedule(None) == Verdict(False, "unknown")
