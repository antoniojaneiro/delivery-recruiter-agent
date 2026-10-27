"""D70: what a recruiter must act on is defined once. The same rule answers in Python for one record and in SQL for
the counters, and a test fills a database with every combination to prove they agree."""
from datetime import datetime
from itertools import product

import pytest

from sazon.client import SAZON_CALENDAR
from screener.model import Outcome, RecruiterStatus
from screener.recruiter_rules import AGENT_CLOSED, BLOCKED, NEEDS_REVIEW, STALLED, TO_CONTACT
from screener.store import Store

T = datetime(2026, 10, 25, 10, 0)
OUTCOMES = [o.value for o in Outcome]
REASONS = ([], ["NO_CONSENT"], ["NO_LICENSE"])


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)
    slot = 0
    for n, (outcome, status, reasons, booked) in enumerate(product(OUTCOMES, RecruiterStatus, REASONS, (False, True))):
        cid = f"c{n}"
        store.commit_turn(cid, T, {}, {}, outcome, [], [], reasons=reasons)
        if status != RecruiterStatus.NEW:
            store.set_status(cid, status, "Ana", T)
        if booked:
            slot = store.add_slot("ES", datetime(2027, 6, 15, 9 + slot % 8, 0), "Ana", "Ana", T.astimezone())
            store.book_slot(slot, cid, T.astimezone())
            slot += 1
    return store


@pytest.mark.parametrize("rule", [NEEDS_REVIEW, TO_CONTACT, BLOCKED, STALLED, AGENT_CLOSED])
def test_the_sql_and_the_python_version_of_a_rule_agree_on_every_combination(store, rule):
    records = store.list_candidates()
    assert len(records) > 200
    assert store.count(rule) == sum(1 for r in records if rule.matches(r))
    assert 0 < store.count(rule) < len(records)


def test_the_rules_say_what_the_dashboard_has_always_meant(store):
    by_id = {r.candidate_id: r for r in store.list_candidates()}
    rejected = next(r for r in by_id.values() if r.outcome == "DISQUALIFIED" and r.reasons == ["NO_LICENSE"]
                    and r.status == RecruiterStatus.NEW)
    declined = next(r for r in by_id.values() if r.outcome == "DISQUALIFIED" and r.reasons == ["NO_CONSENT"])
    assert NEEDS_REVIEW.matches(rejected) and AGENT_CLOSED.matches(rejected)
    assert not NEEDS_REVIEW.matches(declined) and not AGENT_CLOSED.matches(declined)  # declining is the candidate's choice
    reviewed = next(r for r in by_id.values() if r.outcome == "DISQUALIFIED" and r.status != RecruiterStatus.NEW
                    and r.reasons == ["NO_LICENSE"])
    assert not NEEDS_REVIEW.matches(reviewed) and AGENT_CLOSED.matches(reviewed)
    qualified_free = next(r for r in by_id.values() if r.outcome == "QUALIFIED" and r.status == RecruiterStatus.NEW
                          and r.booking is None)
    qualified_booked = next(r for r in by_id.values() if r.outcome == "QUALIFIED" and r.booking)
    assert TO_CONTACT.matches(qualified_free) and not TO_CONTACT.matches(qualified_booked)


def test_the_counters_use_the_same_rules(store):
    numbers = store.kpi_counts()
    assert numbers == {"total": len(store.list_candidates()), "to_review": store.count(NEEDS_REVIEW),
                       "to_contact": store.count(TO_CONTACT), "blocked": store.count(BLOCKED),
                       "stalled": store.count(STALLED)}


def test_the_funnels_closed_by_agent_share_uses_the_same_rule(store):
    counts = store.funnel_counts(("name",))
    assert counts["closed_by_agent"] == store.count(AGENT_CLOSED)
