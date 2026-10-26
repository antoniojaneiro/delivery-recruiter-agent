"""D63: the saved state is declared once, and a changed answer is proposed by a plain function."""
import json
from datetime import date

from sazon.model import Language
from sazon.sazon_spec import SAZON
from sazon.screening import Screening
from sazon.screening_changes import propose_change
from sazon.screening_state import STATE_FIELDS

AREAS = {"Madrid": ["Getafe"], "Guadalajara": []}
TODAY = date(2026, 10, 25)


def propose(field, old, candidate, language=Language.ES):
    return propose_change(SAZON, AREAS, language, field, old, candidate, TODAY)


def test_a_different_valid_answer_is_proposed_with_both_values_in_the_candidates_words():
    assert propose("license", True, False, Language.EN) == ("license", False, "yes", "no")
    assert propose("name", "Juan Pérez", "Carlos López") == ("name", "Carlos López", "Juan Pérez", "Carlos López")


def test_the_same_answer_in_other_words_is_not_a_change():
    assert propose("name", "Juan Pérez", "juan perez") is None
    assert propose("availability", ["full_time", "weekends"], ["weekends", "full_time"]) is None


def test_an_answer_that_would_not_be_accepted_is_not_proposed():
    assert propose("schedule", "morning", "midnight") is None


def test_a_city_is_compared_by_the_area_it_belongs_to():
    assert propose("city", "Madrid", "Getafe") is None
    assert propose("city", "Madrid", "Guadalajara") == ("city", "Guadalajara", "Madrid", "Guadalajara")
    assert propose("city", "Madrid", "Sevilla") == ("city", "Sevilla", "Madrid", "Sevilla")
    assert propose("city", "Madrid", 42) is None


def test_every_saved_key_is_declared_exactly_once():
    keys = [f.key for f in STATE_FIELDS]
    attributes = [f.attribute for f in STATE_FIELDS]
    assert len(keys) == len(set(keys)) and len(attributes) == len(set(attributes))
    assert set(Screening(AREAS).to_state()) == set(keys)


def test_every_declared_attribute_survives_a_save_and_a_load():
    s = Screening(AREAS)
    s.record_consent(True)
    for field, value in {"name": "Ana Ruiz", "experience": (1, ["glovo"]), "start_date": date(2026, 11, 2)}.items():
        s.submit(field, value, TODAY)
    s.submit("city", "Madri", TODAY)  # a near miss: a city confirmation waits
    s.submit("license", False, TODAY)  # a rejection waits
    s.offer_slots([4, 5])
    s.note_unclear_pick()
    s.language = Language.EN
    s.reminder_sent = True
    saved = json.loads(json.dumps(s.to_state()))
    again = Screening.from_state(AREAS, saved)
    assert json.loads(json.dumps(again.to_state())) == saved
    for f in STATE_FIELDS:
        assert getattr(again, f.attribute) == getattr(s, f.attribute), f.attribute
