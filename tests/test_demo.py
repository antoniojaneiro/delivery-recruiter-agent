"""The scenario runner that shows the agent's different responses (framework only: the scenarios'
real replies depend on the model and are looked at by a person)."""
from datetime import datetime

import pytest

from sazon.client import SAZON_CALENDAR
from sazon.spec import SAZON
from sazon import demo
from screener.phrasing import consent_message
from screener.store import Store
from tests.fakes import ScriptedLLM

NOW = datetime(2026, 10, 25, 10, 0)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "demo.db", calendar=SAZON_CALENDAR)


def test_scenarios_have_unique_names_titles_and_messages():
    names = [s.name for s in demo.SCENARIOS]
    assert len(names) == len(set(names)) >= 15
    assert all(s.title and s.messages and all(m.strip() for m in s.messages) for s in demo.SCENARIOS)


def test_the_scenarios_cover_the_hard_cases():
    names = {s.name for s in demo.SCENARIOS}
    assert {"happy_es", "happy_en", "language_switch", "no_license", "car_not_license", "out_of_area",
            "prompt_injection", "unclear_then_blocked", "withdraw", "slot_declined", "correction"} <= names


def test_demo_slots_are_added_for_both_countries(store):
    ids = demo.seed_slots(store, NOW.astimezone())
    slots = store.slots(NOW.astimezone())
    assert len(ids) == len(slots) == 6
    assert {s.country for s in slots} == {"ES", "MX"}


def test_a_scenario_is_played_from_the_disclosure_to_the_last_message(store):
    scenario = demo.Scenario("t", "Test", ["sí", "Juan"])
    lines = []
    result = demo.run_scenario(ScriptedLLM(), store, scenario, NOW, pause=0, write=lines.append)
    assert result.turns[0].bot == consent_message(SAZON)
    assert [t.you for t in result.turns[1:]] == ["sí", "Juan"]
    assert all(t.bot for t in result.turns)
    assert result.outcome == "IN_PROGRESS"
    assert any(line.startswith("you> sí") for line in lines) and any(line.startswith("bot> ") for line in lines)


def test_each_scenario_gets_its_own_candidate(store):
    a = demo.run_scenario(ScriptedLLM(), store, demo.Scenario("a", "A", ["sí"]), NOW, 0, lambda _: None)
    b = demo.run_scenario(ScriptedLLM(), store, demo.Scenario("b", "B", ["no gracias"]), NOW, 0, lambda _: None)
    assert a.candidate_id != b.candidate_id
    assert (a.outcome, b.outcome) == ("IN_PROGRESS", "DISQUALIFIED")


def test_the_markdown_report_has_every_scenario_with_its_replies(store):
    scenario = demo.Scenario("t", "Un título", ["sí"], note="qué se prueba")
    result = demo.run_scenario(ScriptedLLM(), store, scenario, NOW, 0, lambda _: None)
    report = demo.to_markdown([result])
    assert "## Un título" in report and "qué se prueba" in report and "**Candidato:** sí" in report
    assert "Resultado: IN_PROGRESS" in report


def test_the_list_option_prints_the_scenarios_without_calling_the_model(capsys):
    demo.main(["--list"])
    out = capsys.readouterr().out
    assert "happy_es" in out and "prompt_injection" in out


def test_an_unknown_scenario_name_is_reported(capsys):
    with pytest.raises(SystemExit) as error:
        demo.main(["--only", "nope"])
    assert "nope" in str(error.value)
