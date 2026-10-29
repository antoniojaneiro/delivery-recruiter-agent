"""D94: the call page's JavaScript is a real file, run in Node against a fake SDK, microphone and page. Skipped without Node."""
import json
import shutil
import subprocess

import pytest

from tests.support.paths import ROOT

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


@pytest.fixture(scope="module")
def cases():
    done = subprocess.run(["node", str(ROOT / "tests/apps/voice_call.test.mjs"), str(ROOT / "sazon/voice_call.js")],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return {case["name"]: case for case in map(json.loads, done.stdout.splitlines())}


def test_a_call_starts_with_the_session_the_opening_and_the_language_and_says_it_is_listening(cases):
    started = cases["started"]
    assert started["options"]["dynamicVariables"] == {"voice_session": "sess_1", "opening": "Hola"}
    assert started["options"]["signedUrl"] == "wss://x"
    assert started["options"]["overrides"] == {"agent": {"language": "es"}}
    assert "customLlmExtraBody" not in started["options"]  # ElevenLabs refuses a call that sends it
    assert started["status"] == "L" and started["speaking"] == "S" and started["listening"] == "L"


def test_without_a_language_the_agent_keeps_its_own(cases):
    assert "overrides" not in cases["no_language"]["options"]


def test_a_call_that_ends_by_itself_or_by_the_candidate_is_closed_on_the_page_and_an_error_is_not(cases):
    started = cases["started"]
    assert started["end_agent"] == ["E (agent)", 1] and started["end_user"] == ["E (user)", 1]
    assert started["end_error"] == ["E (error)", 0]  # an error stays on screen so its reason can be read
    assert started["end_text"] == "E (closed)" and started["error"] == "X (boom)"


def test_a_page_that_cannot_be_reached_or_has_no_button_does_not_break_the_ending(cases):
    assert cases["page_unreachable"]["end_agent"] == ["E (agent)", 0]
    assert cases["no_button"]["end_agent"] == ["E (agent)", 0]


def test_a_refused_microphone_and_any_other_failure_say_so(cases):
    assert cases["mic_refused"]["status"] == "M" and cases["other_failure"]["status"] == "X"


def test_the_script_cannot_end_the_page_it_is_put_in():
    assert "</script" not in (ROOT / "sazon/voice_call.js").read_text(encoding="utf-8").lower()
