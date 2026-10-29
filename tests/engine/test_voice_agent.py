"""D93: making the ElevenLabs agent that speaks for the engine. It is private (only calls our server signs may start it), its brain
is our endpoint, its first words are the exact AI disclosure, and nothing is kept longer than needed. The calls to the
ElevenLabs REST API are checked here against a fake server, so what is sent is verified; that ElevenLabs accepts it is
checked only live."""
import json

import httpx
import pytest

from sazon import config
from screener.phrasing import consent_message
from screener.voice_agent import ElevenLabs, VoiceSetupError, agent_config, provision
from tests.support.clients import client_for

CLIENT = client_for(config.AREAS)
URL = "https://quiet-example.trycloudflare.com"


def test_the_first_words_are_set_for_each_call_and_default_to_the_exact_disclosure_and_cannot_be_interrupted():
    made = agent_config(CLIENT, URL, "secret_1")
    agent = made["conversation_config"]["agent"]
    assert agent["first_message"] == "{{opening}}" and agent["disable_first_message_interruptions"] is True
    assert agent["dynamic_variables"]["dynamic_variable_placeholders"]["opening"] == consent_message(CLIENT.spec)
    assert made["name"] == f"{CLIENT.spec.pack.company} voice agent"


def test_a_call_may_set_its_own_language_and_nothing_else_may_be_overridden():
    settings = agent_config(CLIENT, URL, "secret_1")["platform_settings"]
    assert settings["overrides"] == {"conversation_config_override": {"agent": {"language": True}}}


def test_the_service_areas_and_their_towns_help_the_listener_hear_the_places():
    keywords = agent_config(CLIENT, URL, "secret_1")["conversation_config"]["asr"]["keywords"]
    assert {"Madrid", "Guadalajara", "Zapopan", "Chamberí"} <= set(keywords) and len(keywords) == len(set(keywords))


def test_its_brain_is_our_endpoint_with_a_secret_and_the_session_comes_as_a_dynamic_variable():
    prompt = agent_config(CLIENT, URL, "secret_1")["conversation_config"]["agent"]["prompt"]
    assert prompt["llm"] == "custom-llm" and prompt["prompt"] == "voice_session={{voice_session}}"
    assert prompt["custom_llm"] == {"url": URL + "/v1/chat/completions", "model_id": "screening-engine",
                                    "api_key": {"secret_id": "secret_1"}, "api_type": "chat_completions"}
    placeholders = agent_config(CLIENT, URL, "secret_1")["conversation_config"]["agent"]["dynamic_variables"]
    assert "voice_session" in placeholders["dynamic_variable_placeholders"]


def test_it_is_private_keeps_no_audio_and_almost_no_history():
    settings = agent_config(CLIENT, URL, "secret_1")["platform_settings"]
    assert settings["auth"]["enable_auth"] is True
    assert settings["privacy"] == {"record_voice": False, "retention_days": 1}
    assert "analysis_items" not in settings  # no evaluation or data collection: no third-party model reads what was said


def test_a_voice_can_be_chosen_and_a_call_has_a_time_limit():
    made = agent_config(CLIENT, URL, "secret_1", voice_id="voice_9")
    assert made["conversation_config"]["tts"]["voice_id"] == "voice_9"
    assert made["conversation_config"]["conversation"]["max_duration_seconds"] == 900
    assert "voice_id" not in agent_config(CLIENT, URL, "secret_1")["conversation_config"]["tts"]


class Fake:
    """A fake ElevenLabs: records the calls and answers like the real API is documented to."""

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.api = ElevenLabs("key-123", transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, dict(request.url.params), request.headers.get("xi-api-key"), body))
        if self.fail:
            return httpx.Response(401, json={"detail": {"message": "key-123 is not valid"}})
        if request.url.path == "/v1/convai/secrets":
            return httpx.Response(200, json={"secret_id": "secret_77", "name": body["name"]})
        if request.url.path == "/v1/convai/agents/create":
            return httpx.Response(200, json={"agent_id": "agent_55"})
        if request.url.path == "/v1/convai/conversation/get-signed-url":
            return httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/convai?conversation_signature=abc"})
        return httpx.Response(200, json={})


def test_provisioning_makes_a_secret_and_an_agent_once_and_later_only_moves_the_address(tmp_path):
    fake, state = Fake(), tmp_path / "voice.json"
    first = provision(fake.api, CLIENT, URL, state, make_secret=lambda: "the-shared-secret")
    assert first.agent_id == "agent_55" and first.secret == "the-shared-secret"
    assert [(m, p) for m, p, *_ in fake.calls] == [("POST", "/v1/convai/secrets"), ("POST", "/v1/convai/agents/create")]
    assert all(call[3] == "key-123" for call in fake.calls)  # the key goes in the header, never in the address
    assert fake.calls[0][4] == {"type": "new", "name": "screening-voice", "value": "the-shared-secret"}
    fake.calls.clear()
    again = provision(fake.api, CLIENT, "https://new-example.trycloudflare.com", state, make_secret=lambda: "other")
    assert again.agent_id == "agent_55" and again.secret == "the-shared-secret"  # the same agent and the same secret
    [(method, path, _, _, body)] = fake.calls
    assert (method, path) == ("PATCH", "/v1/convai/agents/agent_55")
    assert body["conversation_config"]["agent"]["prompt"]["custom_llm"]["url"] == "https://new-example.trycloudflare.com/v1/chat/completions"


def test_the_saved_state_holds_no_api_key(tmp_path):
    fake, state = Fake(), tmp_path / "voice.json"
    provision(fake.api, CLIENT, URL, state, make_secret=lambda: "the-shared-secret")
    assert "key-123" not in state.read_text(encoding="utf-8")


def test_a_signed_url_is_asked_for_with_the_key_in_a_header(tmp_path):
    fake = Fake()
    assert fake.api.signed_url("agent_55").startswith("wss://")
    assert fake.calls == [("GET", "/v1/convai/conversation/get-signed-url", {"agent_id": "agent_55"}, "key-123", None)]


def test_a_refusal_is_reported_without_the_key_in_the_message(tmp_path):
    fake = Fake(fail=True)
    with pytest.raises(VoiceSetupError) as error:
        provision(fake.api, CLIENT, URL, tmp_path / "voice.json", make_secret=lambda: "s")
    assert "401" in str(error.value) and "key-123" not in str(error.value)


def test_the_agent_has_the_end_call_tool_so_our_endpoint_can_finish_a_call():
    tools = agent_config(CLIENT, URL, "secret_1")["conversation_config"]["agent"]["prompt"]["built_in_tools"]
    assert tools == {"end_call": {"type": "system", "name": "end_call", "description": "",
                                  "params": {"system_tool_type": "end_call"}}}
