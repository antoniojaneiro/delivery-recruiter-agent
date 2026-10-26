"""D46: the recruiter's summary card is built by code from saved data, always in Spanish."""
from datetime import date, datetime

import pytest

from tests.clients import client_for
from sazon.sazon_spec import SAZON
from sazon import session
from sazon.model import Language
from sazon.screening import Screening
from sazon.store import Store
from sazon.summary import summarise

AREAS = {"Madrid": [], "Guadalajara": []}
TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 10, 0)

ANSWERS = {
    "name": "Juan Pérez", "experience": (2, ["glovo", "uber eats"]), "availability": ["full_time"],
    "schedule": "morning", "start_date": date(2026, 11, 1), "city": "Madrid", "license": True,
}


def screening(**overrides):
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    answers = {**ANSWERS, **overrides}
    for field, value in answers.items():
        if value is not None:
            s.submit(field, value, TODAY)
    return s


def test_a_qualified_candidate_gets_a_complete_card():
    card = summarise(screening())
    lines = card.splitlines()
    assert lines[0] == "Juan Pérez · Madrid · Cualificado"
    for expected in ["Licencia: sí", "Experiencia: 2 años (glovo, uber eats)", "Disponibilidad: tiempo completo",
                     "Horario preferido: mañana", "Inicio: 2026-11-01"]:
        assert expected in lines
    assert not any(line.startswith("Falta") for line in lines)
    assert lines[-1] == "Resumen automático: la decisión final es del reclutador."


def test_no_experience_is_stated_plainly():
    assert "Experiencia: sin experiencia" in summarise(screening(experience=(0, []))).splitlines()


def test_several_availabilities_and_schedules_use_spanish_labels():
    card = summarise(screening(availability=["part_time", "weekends"], schedule="flexible"))
    assert "Disponibilidad: medio tiempo, fines de semana" in card and "Horario preferido: flexible" in card


def test_no_license_shows_the_reason_in_plain_spanish():
    s = screening(license=None)
    s.submit("license", False, TODAY)
    s.confirm_rejection(True)
    card = summarise(s)
    assert "Descartado por el agente" in card.splitlines()[0]
    assert "Motivo: no tiene licencia de conducir" in card and "Licencia: no" in card


def test_an_out_of_area_city_is_shown_with_the_candidates_own_city():
    s = screening(city=None)
    s.submit("city", "Sevilla", TODAY)
    s.confirm_rejection(True)
    card = summarise(s)
    assert "Motivo: fuera de la zona de servicio" in card and "Sevilla" in card.splitlines()[0]


def test_a_refused_consent_card_holds_no_personal_data():
    s = Screening(AREAS, SAZON)
    s.record_consent(False)
    card = summarise(s)
    assert "no dio su consentimiento" in card and "Licencia" not in card and "Falta" not in card


def test_a_blocked_candidate_says_what_has_not_been_provided():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    for _ in range(6):
        s.submit("name", "Juan", TODAY)
    card = summarise(s)
    assert "Bloqueado" in card.splitlines()[0] and "Motivo: no ha indicado su nombre" in card
    assert "Falta: nombre" in card


def test_a_half_finished_chat_lists_what_is_missing_in_order():
    card = summarise(screening(schedule=None, city=None))
    assert card.splitlines()[0].endswith("En curso")
    assert "Falta: horario preferido, ciudad" in card


def test_a_start_date_beyond_12_weeks_is_flagged():
    assert "Aviso: la fecha de inicio está a más de 12 semanas" in summarise(screening(start_date=date(2027, 6, 1)))


def test_chat_facts_are_listed_without_any_judgement_of_the_person():
    s = screening()
    s.language = Language.EN
    s.human_requested()
    line = [l for l in summarise(s).splitlines() if l.startswith("Chat:")][0]
    assert "idioma inglés" in line and "pidió hablar con una persona" in line


def test_clarifications_asked_are_counted():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.submit("name", "Juan", TODAY)
    s.submit("name", "Juan", TODAY)
    assert "2 aclaraciones" in summarise(s)


@pytest.mark.parametrize("prepare,label", [
    (lambda s: s.withdraw(), "Se retiró"),
    (lambda s: (s.off_topic(), s.off_topic(), s.off_topic()), "Terminó fuera de tema"),
    (lambda s: (s.send_reminder(), s.mark_stalled()), "Sin respuesta"),
])
def test_other_outcomes_have_spanish_labels(prepare, label):
    s = screening(city=None)
    prepare(s)
    assert card_outcome(summarise(s)) == label


def card_outcome(card):
    return card.splitlines()[0].split(" · ")[-1]


def test_a_stalled_candidate_notes_that_a_reminder_was_sent():
    s = screening(city=None)
    s.send_reminder()
    s.mark_stalled()
    assert "recordatorio enviado" in summarise(s)


def test_the_candidates_own_words_never_reach_the_card():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.submit("name", "Juan", TODAY, raw="mi contraseña es 1234 y soy un tipo muy simpático")
    card = summarise(s)
    assert "contraseña" not in card and "simpático" not in card


def test_the_card_is_saved_with_every_turn_and_refreshed(tmp_path):
    store = Store(tmp_path / "s.db")
    s = session.load(store, "c1", client_for(AREAS))
    s.record_consent(True)
    session.commit(store, "c1", s, NOW)
    first = store.get("c1").summary
    s.submit("name", "Juan Pérez", TODAY)
    session.commit(store, "c1", s, NOW)
    assert "En curso" in first and "Juan Pérez" not in first
    assert store.get("c1").summary.startswith("Juan Pérez")
