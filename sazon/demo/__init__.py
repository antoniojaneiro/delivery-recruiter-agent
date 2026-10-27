"""Plays scripted candidate conversations through the real agent so a person can read its replies."""
from sazon.demo.runner import Result, Turn, main, run_scenario, seed_slots, to_markdown  # noqa: F401
from sazon.demo.scenarios import BY_NAME, SCENARIOS, Scenario  # noqa: F401

__all__ = ["BY_NAME", "SCENARIOS", "Result", "Scenario", "Turn", "main", "run_scenario", "seed_slots", "to_markdown"]
