"""D79: what the calendar page needs, as plain code: the week a day belongs to, which call times fall in it, and which
candidates a recruiter may schedule a call for."""
from datetime import date, datetime

import pytest

from tests.support.tables import table

from screener.calendar_view import week_slots, week_start
from screener.model import RecruiterStatus as S
from screener.recruiter_rules import can_schedule
from screener.store import Record, Slot


def slot(n, country, when):
    return Slot(n, country, when, None, None, False)


def record(outcome="QUALIFIED", status=S.NEW, booking=None):
    return Record("c", {}, {}, None, outcome, datetime(2026, 11, 1), [], [], status, booking)


@table("day,monday", [
    (date(2026, 11, 2), date(2026, 11, 2)), (date(2026, 11, 4), date(2026, 11, 2)), (date(2026, 11, 8), date(2026, 11, 2)),
    (date(2026, 11, 9), date(2026, 11, 9)), (date(2026, 1, 1), date(2025, 12, 29))])
def test_a_week_starts_on_monday(day, monday):
    assert week_start(day) == monday


def test_the_week_has_seven_days_and_holds_only_that_countrys_times_in_clock_order():
    monday = date(2026, 11, 2)
    slots = [slot(1, "ES", datetime(2026, 11, 3, 16, 0)), slot(2, "ES", datetime(2026, 11, 3, 9, 30)),
             slot(3, "MX", datetime(2026, 11, 3, 10, 0)), slot(4, "ES", datetime(2026, 11, 9, 10, 0)),
             slot(5, "ES", datetime(2026, 11, 1, 10, 0)), slot(6, "ES", datetime(2026, 11, 8, 23, 0))]
    week = week_slots(slots, monday, "ES")
    assert list(week) == [date(2026, 11, d) for d in range(2, 9)]
    assert [s.id for s in week[date(2026, 11, 3)]] == [2, 1]
    assert [s.id for s in week[date(2026, 11, 8)]] == [6]
    assert week[date(2026, 11, 2)] == [] and sum(len(v) for v in week.values()) == 3


@table("outcome,status,expected", [
    ("QUALIFIED", S.NEW, True), ("QUALIFIED", S.QUALIFIED, True), ("QUALIFIED", S.INTERVIEW_SCHEDULED, True),
    ("QUALIFIED", S.CONTACTED, False),  # a recruiter put them back to "conversation going"
    ("QUALIFIED", S.HIRED, False), ("QUALIFIED", S.REJECTED, False), ("QUALIFIED", S.UNREACHABLE, False),
    ("DISQUALIFIED", S.NEW, False), ("DISQUALIFIED", S.CONTACTED, False), ("DISQUALIFIED", S.QUALIFIED, True),  # overruled
    ("IN_PROGRESS", S.NEW, False),
    ("STALLED", S.NEW, False), ("BLOCKED", S.NEW, False), ("WITHDRAWN", S.NEW, False), (None, S.NEW, False)])
def test_a_call_can_be_organised_for_the_states_qualified_and_interview_scheduled_whoever_decided_it(outcome, status, expected):
    assert can_schedule(record(outcome, status)) is expected


def test_a_qualified_candidate_who_already_has_a_call_can_be_scheduled_to_move_it():
    from screener.store import Booking
    assert can_schedule(record(booking=Booking(1, "ES", datetime(2026, 11, 4, 10, 0), None))) is True
