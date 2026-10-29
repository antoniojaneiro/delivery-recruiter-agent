"""Problems seen when the scenario runner played real conversations on the real model (D50)."""
from datetime import date, datetime

import pytest

from sazon.areas import AREAS
from tests.support.tables import table

from sazon.client import SAZON_CLIENT
from screener import turn
from screener.consent import read_consent
from sazon.spec import SAZON, Extraction
from sazon.fields import Field
from screener.directive import Directive, Kind
from screener.phrasing import consent_message, phrase
from screener.screening import Screening
from screener.store import Store
from tests.support.fakes import FakeLLM, ScriptedLLM

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 10, 0)


# --- a greeting before the yes must not lose the whole conversation -------------------------------

@table("text", [
    "hola, sí", "Hola! Sí", "hola sí", "Hola, vale", "buenas tardes, sí", "buenos días, claro", "hi, yes",
    "Hello, yes please", "hey yes", "hola, sí, no hay problema",
])
def test_a_greeting_before_a_clear_yes_is_still_a_yes(text):
    assert read_consent(text).answer is True


@table("text", ["hola, no gracias", "Hello, no thanks", "buenas, no"])
def test_a_greeting_before_a_clear_no_is_still_a_no(text):
    assert read_consent(text).answer is False


@table("text", ["hola", "Hola!", "buenos días", "hello", "hey", "hola, ¿quién eres?", "hola, soy Juan"])
def test_a_greeting_alone_or_with_something_else_is_unclear(text):
    assert read_consent(text).answer is None


# --- hesitation is not off-topic -------------------------------------------------------------------

@table("filler", ["mmm", "no sé", "jaja", "ok", "pues", "eh", "bueno", "ni idea", "hmm", "idk", "lol"])
def test_hesitation_flagged_as_off_topic_by_the_model_does_not_count_as_off_topic(filler):
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    for _ in range(4):
        s.apply(Extraction(off_topic=True), filler, TODAY)
    assert s.decide().outcome == "IN_PROGRESS"
    assert [kind for kind, _ in s.events].count("off_topic") == 0
    assert [kind for kind, _ in s.events].count("follow_up") == 4


def test_real_off_topic_messages_still_count_and_still_end_the_chat():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.apply(Extraction(off_topic=True), "¿cuál es la capital de Francia?", TODAY)
    s.apply(Extraction(off_topic=True), "cuéntame un chiste", TODAY)
    s.apply(Extraction(off_topic=True), "¿qué opinas del fútbol?", TODAY)
    assert s.decide().outcome == "ENDED_OFF_TOPIC"


def test_unclear_answers_now_reach_the_block_instead_of_ending_the_chat_early():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    for filler in ["mmm", "no sé", "jaja", "ok", "pues", "eh", "bueno"]:
        s.apply(Extraction(off_topic=True), filler, TODAY)
    assert s.decide().outcome == "BLOCKED" and s.decide().reasons == ["BLOCKED_ON_NAME"]


def test_the_prompt_says_hesitation_is_not_off_topic():
    from sazon.spec import SYSTEM
    assert "mmm" in SYSTEM and "NOT off_topic" in SYSTEM


# --- no greeting in the middle of a conversation ------------------------------------------------

@table("raw,expected", [
    ("¡Hola! ¿En qué ciudad vives? 🚚", "¿En qué ciudad vives? 🚚"),
    ("Hola, ¿cuál es tu ciudad?", "¿Cuál es tu ciudad?"),
    ("¡Hola! Bienvenido a Grupo Sazón. 🚚 ¿Cuándo podrías empezar?", "🚚 ¿Cuándo podrías empezar?"),
    ("¡Hola! 👋 Para conocerte mejor, ¿cuántos años tienes de experiencia?", "👋 Para conocerte mejor, ¿cuántos años tienes de experiencia?"),
])
def test_a_leading_greeting_or_welcome_is_removed_from_a_phrased_question(raw, expected):
    assert phrase(FakeLLM(raw), SAZON, Directive(Kind.ASK, field=Field.CITY), "es") == expected


@table("raw,expected", [
    ("Hey! What city do you live in?", "What city do you live in?"),
    ("Hi there! Which city do you live in?", "Which city do you live in?"),
    ("Hello, what is your city?", "What is your city?"),
])
def test_the_same_in_english(raw, expected):
    assert phrase(FakeLLM(raw), SAZON, Directive(Kind.ASK, field=Field.CITY), "en") == expected


def test_a_reply_that_is_only_a_greeting_falls_back_to_the_fixed_question():
    out = phrase(FakeLLM("¡Hola!"), SAZON, Directive(Kind.ASK, field=Field.CITY), "es")
    assert "ciudad" in out.lower()


def test_the_phrasing_prompt_forbids_greeting_again():
    llm = FakeLLM("¿Y tu ciudad?")
    phrase(llm, SAZON, Directive(Kind.ASK, field=Field.CITY), "es")
    assert "greet" in llm.calls[0]["system"].lower()


# --- asking for a person or about pay gets an answer ---------------------------------------------

def test_asking_for_a_person_is_acknowledged_before_the_next_question():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    directive = s.apply(Extraction(wants_human=True), "¿puedo hablar con una persona?", TODAY)
    out = phrase(FakeLLM("¿Cómo te llamas?"), SAZON, directive, "es")
    assert out.startswith("Soy Sofía, una asistente virtual") and "reclutador" in out and out.endswith("¿Cómo te llamas?")


def test_asking_about_pay_says_a_recruiter_will_answer():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    directive = s.apply(Extraction(asks_pay=True), "¿cuánto pagan?", TODAY)
    out = phrase(FakeLLM("¿Cómo te llamas?"), SAZON, directive, "es")
    assert "sueldo" in out and "reclutador" in out and out.endswith("¿Cómo te llamas?")
    assert s.decide().outcome == "IN_PROGRESS" and [k for k, _ in s.events].count("off_topic") == 0


def test_both_questions_in_one_message_get_both_answers_once():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    directive = s.apply(Extraction(wants_human=True, asks_pay=True), "¿hablo con alguien y cuánto pagan?", TODAY)
    out = phrase(FakeLLM("¿Cómo te llamas?"), SAZON, directive, "es")
    assert out.count("reclutador") >= 1 and "sueldo" in out and "asistente virtual" in out


def test_the_english_notices():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.language = "en"
    directive = s.apply(Extraction(wants_human=True, asks_pay=True), "can I talk to someone? what is the pay?", TODAY)
    out = phrase(FakeLLM("What is your name?"), SAZON, directive, "en")
    assert "virtual assistant" in out and "pay" in out and out.endswith("What is your name?")


def test_a_notice_is_not_repeated_on_the_next_turn():
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    s.apply(Extraction(asks_pay=True), "¿cuánto pagan?", TODAY)
    again = s.apply(Extraction(name="Juan"), "Juan", TODAY)
    assert again.notices == ()


def test_the_extraction_schema_and_prompt_know_the_pay_flag():
    from sazon.spec import SYSTEM
    assert Extraction.model_validate({"asks_pay": True}).asks_pay is True and "asks_pay" in SYSTEM


def test_through_a_full_turn_the_reply_acknowledges_a_request_for_a_person(tmp_path):
    store = Store(tmp_path / "s.db")
    turn.start(store, SAZON_CLIENT, "c1", NOW)
    turn.handle_message(ScriptedLLM(), store, SAZON_CLIENT, "c1", "sí", NOW)
    llm = ScriptedLLM([{"wants_human": True}], ["¿Cómo te llamas?"])
    reply = turn.handle_message(llm, store, SAZON_CLIENT, "c1", "¿puedo hablar con una persona?", NOW)
    assert "asistente virtual" in reply and "reclutador" in reply
    assert "human_requested" in [e.type for e in store.events("c1")]


# --- closings are not repeated word for word -------------------------------------------------------

def talk(store, message, *extractions):
    return turn.handle_message(ScriptedLLM(extractions), store, SAZON_CLIENT, "c1", message, NOW)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def reject(store):
    turn.start(store, SAZON_CLIENT, "c1", NOW)
    talk(store, "sí")
    talk(store, "no tengo licencia", {"has_license": False})
    return talk(store, "sí, correcto", {"confirms_rejection": True})


def test_a_message_after_a_rejection_gets_a_short_note_not_the_same_close(store):
    first = reject(store)
    again = talk(store, "gracias")
    assert "no puedo seguir con el proceso automático" in first
    assert again != first and "ya está cerrada" in again and len(again) < len(first)


def test_a_qualified_candidate_who_writes_again_is_told_once_more_without_the_celebration(store):
    turn.start(store, SAZON_CLIENT, "c1", NOW)
    talk(store, "sí")
    for message, ex in [("Soy Juan Pérez", {"name": "Juan Pérez"}), ("sin experiencia", {"no_experience": True}),
                        ("tiempo completo", {"availability": ["full_time"]}), ("mañana", {"schedule": "morning"}),
                        ("ya", {"start_date": {"now": True}}), ("Madrid", {"city": "Madrid"})]:
        talk(store, message, ex)
    first = talk(store, "sí tengo", {"has_license": True})
    again = talk(store, "gracias")
    assert "tu perfil encaja" in first
    assert "tu perfil encaja" not in again and "horarios libres" in again and "48" not in again


def test_a_third_message_gets_the_same_short_note_again(store):
    reject(store)
    second, third = talk(store, "gracias"), talk(store, "hola")
    assert second == third
