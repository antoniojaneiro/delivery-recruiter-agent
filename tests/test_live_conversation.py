"""One full fictional conversation through handle_message on the real model.
Run with: python -m pytest -m live -q -k conversation   (needs GEMINI_API_KEY; fictional data only)"""
import os
import time
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv

from sazon.sazon_client import SAZON_CLIENT
from sazon import turn
from sazon.store import Store

load_dotenv()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set"),
]
RETRY_WAIT_SECONDS = 40
PAUSE_SECONDS = 4  # the free tier allows only a handful of requests per minute


def show(transcript):
    """The whole conversation as text: pytest would truncate a list in the failure message."""
    lines = [f"> {message}\n< {reply}" for message, reply in transcript]
    return "\n" + "\n".join(lines)


@pytest.fixture(scope="module")
def llm():
    from sazon import gemini

    return gemini.from_env()


def test_a_candidate_goes_from_consent_to_a_booked_call(tmp_path, llm):
    store = Store(tmp_path / "live.db")
    now = datetime.now()
    day = (now + timedelta(days=14)).replace(hour=9, minute=0, second=0, microsecond=0)
    slot_ids = [store.add_slot("MX", day + timedelta(days=i), "Luis", "Luis", now.astimezone()) for i in range(3)]

    transcript = []

    def say(message):
        time.sleep(PAUSE_SECONDS)
        reply = turn.handle_message(llm, store, SAZON_CLIENT, "live1", message, datetime.now())
        if "problema técnico" in reply or "technical problem" in reply:
            time.sleep(RETRY_WAIT_SECONDS)  # most likely the free-tier rate limit; a failed turn costs nothing (D39)
            reply = turn.handle_message(llm, store, SAZON_CLIENT, "live1", message, datetime.now())
        transcript.append((message, reply))
        assert reply.strip(), show(transcript)
        assert "problema técnico" not in reply and "technical problem" not in reply, show(transcript)
        assert len(reply) < 700, show(transcript)
        return reply

    turn.start(store, SAZON_CLIENT, "live1", now)
    say("sí")
    assert "llamas" in transcript[-1][1].lower() or "nombre" in transcript[-1][1].lower(), show(transcript)

    unclear = say("Carlos")
    assert "carlos" not in store.get("live1").extracted.get("name", "").lower(), show(transcript)
    assert unclear

    say("Carlos Ruiz Mora")
    assert store.get("live1").extracted["name"] == "Carlos Ruiz Mora", show(transcript)

    english = say("I have 2 years of experience with Glovo")
    assert store.get("live1").extracted["experience"]["years"] == 2, show(transcript)
    assert "¿" not in english and "disponibilidad" not in english.lower(), transcript  # switched to English

    for message in ["I can work full time", "mornings are best for me", "I can start next week"]:
        reply = say(message)
        assert "¿" not in reply, show(transcript)

    typo = say("I live in Guadalajra")
    assert "Guadalajara" in typo, show(transcript)
    say("yes, that's right")
    assert store.get("live1").extracted.get("city") == "Guadalajara", show(transcript)

    offer = say("yes, I have a driver's license")
    record = store.get("live1")
    assert record.outcome == "QUALIFIED", show(transcript)
    assert all(f"{i})" in offer for i in (1, 2, 3)) and "48" in offer, show(transcript)

    confirmation = say("2")
    assert store.booking_of("live1").slot_id == slot_ids[1], show(transcript)
    assert "booked" in confirmation.lower(), show(transcript)

    extracted = store.get("live1").extracted
    assert extracted["availability"] == ["full_time"] and extracted["schedule"] == "morning", show(transcript)
    assert extracted["license"] is True and extracted["experience"]["platforms"] == ["glovo"], show(transcript)
    assert store.get("live1").summary.startswith("Carlos Ruiz Mora · Guadalajara · Cualificado")
