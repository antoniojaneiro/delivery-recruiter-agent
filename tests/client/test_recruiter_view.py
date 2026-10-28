"""What the recruiter dashboard shows, as plain functions (no Streamlit)."""
from datetime import datetime, timezone

import pytest

from tests.support.tables import table

from sazon.client import SAZON_CALENDAR
from sazon.spec import SAZON
from screener.model import RecruiterStatus
from screener.model import Outcome
from screener.recruiter_view import BADGE_COLORS, OUTCOME_COLOR, STATUS_COLOR, filter_records, matches
from sazon.recruiter_view import view_for
from screener.store import Store

T1 = datetime(2026, 10, 25, 10, 0)
T2 = datetime(2026, 10, 26, 9, 30)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.db", calendar=SAZON_CALENDAR)

    def add(cid, name, city, outcome, now=T1, reasons=()):
        extracted = {k: v for k, v in (("name", name), ("city", city)) if v}
        s.commit_turn(cid, now, {}, extracted, outcome, [], [], reasons=list(reasons))

    add("c1", "Juan Pérez", "Madrid", "QUALIFIED")
    add("c2", "María García-López", "Guadalajara", "QUALIFIED", T2)
    add("c3", "Ana Ruiz", "Sevilla", "DISQUALIFIED", reasons=["OUT_OF_AREA"])
    add("c4", None, None, "BLOCKED", reasons=["BLOCKED_ON_NAME"])
    add("c5", "Luis Soto", "Madrid", "STALLED")
    s.set_status("c2", RecruiterStatus.CONTACTED, "Ana", T2)
    return s


def ids(records):
    return [r.candidate_id for r in records]


def test_every_outcome_and_status_has_a_spanish_label():
    view = view_for("es")
    assert [view.outcome_label(o) for o in Outcome] and all(view.status_label(s) for s in RecruiterStatus)
    assert view.outcome_label("QUALIFIED") == "Cualificado" and view.status_label("interview_scheduled") == "Entrevista programada"
    assert view_for("en").outcome_label("QUALIFIED") == "Qualified"


def test_the_table_has_one_row_per_candidate_with_spanish_columns(store):
    rows = view_for("es").table_rows(store.list_candidates())
    row = next(r for r in rows if r["Id"] == "c2")
    assert row["Nombre"] == "María García-López" and row["Ciudad"] == "Guadalajara"
    assert row["Agente"] == "Cualificado" and row["Reclutador"] == "Contactado"
    assert row["Actualizado"] == "2026-10-26 09:30"


def test_a_candidate_without_a_name_is_still_listed(store):
    row = next(r for r in view_for("es").table_rows(store.list_candidates()) if r["Id"] == "c4")
    assert row["Nombre"] == "(sin nombre)" and row["Agente"] == "Bloqueado"


@table("text,expected", [
    ("garcia", ["c2"]), ("GARCÍA LOPEZ", ["c2"]), ("juan", ["c1"]), ("madrid", ["c1", "c5"]),
    ("sevilla", ["c3"]), ("c4", ["c4"]), ("   ", ["c1", "c2", "c3", "c4", "c5"]), ("zzz", []),
])
def test_search_ignores_accents_and_case_and_looks_at_name_city_and_id(store, text, expected):
    found = [r for r in store.list_candidates() if matches(r, text, SAZON)]
    assert sorted(ids(found)) == sorted(expected)


def test_filters_combine_outcome_status_and_search(store):
    records = store.list_candidates()
    assert sorted(ids(filter_records(records, outcomes=["QUALIFIED"], statuses=[], search="", spec=SAZON))) == ["c1", "c2"]
    assert ids(filter_records(records, outcomes=["QUALIFIED"], statuses=["new"], search="", spec=SAZON)) == ["c1"]
    assert ids(filter_records(records, outcomes=[], statuses=["contacted"], search="garcia", spec=SAZON)) == ["c2"]
    assert len(filter_records(records, outcomes=[], statuses=[], search="", spec=SAZON)) == 5


def test_the_key_numbers_count_what_a_recruiter_must_act_on(store):
    numbers = store.kpi_counts()
    assert numbers == {"total": 5, "to_contact": 1, "to_review": 1, "blocked": 1, "stalled": 1}


def test_a_booked_call_shows_in_the_table_and_leaves_the_to_contact_number(store):
    view = view_for("es")
    store.commit_turn("c1", T1, {}, {"name": "Juan Pérez"}, "QUALIFIED", [], [])
    slot_id = store.add_slot("ES", datetime(2027, 6, 15, 10, 0), "Ana", "Ana", T1.astimezone())
    before = store.kpi_counts()["to_contact"]
    store.book_slot(slot_id, "c1", T1.astimezone())
    records = store.list_candidates()
    row = next(r for r in view.table_rows(records) if r["Id"] == "c1")
    assert row["Llamada"] == "mar 15 jun, 10:00 (España)"
    assert store.kpi_counts()["to_contact"] == before - 1
    assert view.call_label(next(r for r in records if r.candidate_id == "c1").booking) == "mar 15 jun, 10:00 (España)"
    assert view.call_label(None) == ""
    assert next(r for r in view.table_rows(records) if r["Id"] == "c2")["Llamada"] == ""


def test_the_slot_state_says_when_a_free_slot_is_too_close_to_be_offered():
    from screener.store import Slot
    slot_state = view_for("es").slot_state
    soon = Slot(1, "ES", datetime(2026, 10, 26, 10, 30), None, None, False)
    later = Slot(2, "ES", datetime(2026, 11, 3, 10, 0), None, None, False)
    taken = Slot(3, "ES", datetime(2026, 11, 3, 11, 0), None, "c1", False)
    now = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)  # a fixed instant, independent of this machine's zone
    assert slot_state(later, None, now) == "Libre"
    assert slot_state(soon, None, now) == "Ya no se ofrece (faltan menos de 2 horas)"
    assert slot_state(taken, "Juan Pérez", now) == "Reservado: Juan Pérez (c1)"


def test_the_review_queue_holds_agent_rejections_nobody_has_looked_at(store):
    from screener.recruiter_rules import NEEDS_REVIEW
    needs_review = NEEDS_REVIEW.matches
    records = {r.candidate_id: r for r in store.list_candidates()}
    assert needs_review(records["c3"])          # DISQUALIFIED for OUT_OF_AREA, status new
    assert not needs_review(records["c1"])      # qualified
    store.commit_turn("x1", T1, {}, {}, "DISQUALIFIED", [], [], reasons=["NO_CONSENT"])
    store.commit_turn("x2", T1, {}, {}, "ENDED_OFF_TOPIC", [], [])
    store.commit_turn("x3", T1, {}, {}, "DISQUALIFIED", [], [], reasons=["NO_LICENSE"])
    store.set_status("x3", RecruiterStatus.REJECTED, "Ana", T1)
    after = {r.candidate_id: r for r in store.list_candidates()}
    assert not needs_review(after["x1"]) and needs_review(after["x2"]) and not needs_review(after["x3"])
    assert store.kpi_counts()["to_review"] == 2


def test_the_review_only_filter_keeps_just_the_queue(store):
    records = store.list_candidates()
    assert ids(filter_records(records, outcomes=[], statuses=[], search="", spec=SAZON, review_only=True)) == ["c3"]


def test_markdown_in_a_name_is_shown_as_text():
    from screener.recruiter_view import escape_markdown
    nasty = "**Juan** [clic](http://evil.example) ![x](http://evil.example/p.png) <b>#a_b`c`"
    escaped = escape_markdown(nasty)
    for char in "*[]()!<#_`":
        assert escaped.count(char) == escaped.count("\\" + char), char
    assert escape_markdown("María García-López") == "María García-López"


def test_the_notice_period_shown_to_recruiters_comes_from_the_one_rule():
    from sazon.client import SAZON_CALENDAR
    from screener.store import Slot
    slot_state = view_for("es").slot_state
    soon = Slot(1, "ES", datetime(2026, 10, 26, 10, 30), None, None, False)
    now = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)
    hours = int(SAZON_CALENDAR.min_notice.total_seconds() // 3600)
    assert f"menos de {hours} horas" in slot_state(soon, None, now)


# --- badges (D66) ---------------------------------------------------------------------------------------------

def test_every_outcome_and_status_has_a_badge_color_and_the_colors_tell_good_from_bad():
    assert set(OUTCOME_COLOR) == set(Outcome) and set(STATUS_COLOR) == set(RecruiterStatus)
    assert set(OUTCOME_COLOR.values()) | set(STATUS_COLOR.values()) <= BADGE_COLORS
    assert OUTCOME_COLOR[Outcome.QUALIFIED] == "green" and OUTCOME_COLOR[Outcome.DISQUALIFIED] == "red"
    assert STATUS_COLOR[RecruiterStatus.HIRED] == "green" and STATUS_COLOR[RecruiterStatus.REJECTED] == "red"


@table("language,qualified", [("es", "Cualificado"), ("en", "Qualified")])
def test_the_badge_columns_list_every_label_with_its_color_in_the_same_order(store, language, qualified):
    view = view_for(language)
    columns = view.badge_columns()
    options, colors = columns[next(iter(columns))]
    assert len(options) == len(colors) and qualified in options
    assert colors[options.index(qualified)] == OUTCOME_COLOR["QUALIFIED"]
    rows = view.badge_rows(view.table_rows(store.list_candidates()))
    first_column = next(iter(columns))
    assert all(isinstance(row[first_column], list) and len(row[first_column]) == 1 for row in rows)


def test_a_text_pack_that_lacks_a_text_the_screens_use_is_refused_when_the_view_is_built():
    from sazon.client import SAZON_CLIENT
    from screener.model import Language
    from screener.recruiter_view import RecruiterView
    from screener.ui_texts import UiPack, UiTextError
    with pytest.raises(UiTextError) as error:
        RecruiterView(SAZON_CLIENT, UiPack((Language.ES,), {"col.id": {Language.ES: "Id"}}))
    assert "status.new" in str(error.value)
