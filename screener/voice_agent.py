"""D93: making the ElevenLabs agent that speaks for the engine, and asking it for a call. The agent is private (only a call our own
server signs may start), its first words are the client's exact AI disclosure, and its brain is the voice endpoint of this
project (`voice_service`): ElevenLabs only listens and speaks. Nothing is kept longer than needed (no audio, one day of
history) and no evaluation or data collection is switched on, so no third-party model reads what a candidate said.

A thin client over the REST API (no SDK to install). The key goes in a header and never into a message or a file."""
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

import httpx

from screener.client import Client
from screener.phrasing import consent_message

API = "https://api.elevenlabs.io"
MAX_CALL_SECONDS = 900  # a screening call is short; the cap also bounds the cost of a call left open


class VoiceSetupError(RuntimeError):
    """ElevenLabs refused or could not be reached. The message never holds the API key."""


@dataclass(frozen=True)
class VoiceState:
    agent_id: str
    secret_id: str
    secret: str  # what ElevenLabs sends to our endpoint as a bearer token


class ElevenLabs:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None, timeout: float = 30.0):
        self._key = api_key
        self._http = httpx.Client(base_url=API, headers={"xi-api-key": api_key}, transport=transport, timeout=timeout)

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise VoiceSetupError(f"could not reach ElevenLabs: {type(error).__name__}") from None
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json().get("detail")
                detail = body.get("message", "") if isinstance(body, dict) else str(body or "")
            except ValueError:
                pass
            detail = detail.replace(self._key, "[key]") if self._key else detail  # an error can quote what was sent
            raise VoiceSetupError(f"ElevenLabs answered {response.status_code} to {method} {path}: {detail[:200]}")
        return response.json()

    def create_secret(self, name: str, value: str) -> str:
        return self._call("POST", "/v1/convai/secrets", json={"type": "new", "name": name, "value": value})["secret_id"]

    def create_agent(self, config: dict) -> str:
        return self._call("POST", "/v1/convai/agents/create", json=config)["agent_id"]

    def update_agent(self, agent_id: str, config: dict) -> None:
        self._call("PATCH", f"/v1/convai/agents/{agent_id}", json=config)

    def signed_url(self, agent_id: str) -> str:
        """A one-time address a browser uses to start a call with a private agent; valid 15 minutes (ElevenLabs)."""
        return self._call("GET", "/v1/convai/conversation/get-signed-url", params={"agent_id": agent_id})["signed_url"]


def agent_config(client: Client, public_url: str, secret_id: str, voice_id: str | None = None) -> dict:
    """The whole agent, as the REST API takes it. `public_url` is where our voice endpoint can be reached from outside."""
    tts = {"model_id": "eleven_flash_v2_5"}  # a multilingual model: it speaks Spanish and English from the text
    if voice_id:
        tts["voice_id"] = voice_id
    return {
        "name": f"{client.spec.pack.company} voice agent",
        "conversation_config": {
            "agent": {
                "first_message": consent_message(client.spec),  # the disclosure and the consent question, word for word
                "disable_first_message_interruptions": True,  # it is always heard in full
                "language": client.spec.pack.default_language.value,
                "dynamic_variables": {"dynamic_variable_placeholders": {"voice_session": "none"}},
                "prompt": {
                    "prompt": "voice_session={{voice_session}}",  # our endpoint reads the session from here (or from extra body)
                    "llm": "custom-llm",
                    "custom_llm": {"url": public_url.rstrip("/") + "/v1/chat/completions", "model_id": "screening-engine",
                                   "api_key": {"secret_id": secret_id}, "api_type": "chat_completions"},
                },
            },
            "tts": tts,
            "asr": {"provider": "scribe_realtime", "quality": "high", "user_input_audio_format": "pcm_16000"},
            "conversation": {"max_duration_seconds": MAX_CALL_SECONDS},
        },
        "platform_settings": {
            "auth": {"enable_auth": True},  # only a call our server signs can start it
            "privacy": {"record_voice": False, "retention_days": 1},
        },
    }


def load_state(path: Path) -> VoiceState | None:
    """The agent and the secret saved by `provision`, or None when the voice agent has not been set up."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return VoiceState(data["agent_id"], data["secret_id"], data["secret"])
    except (OSError, ValueError, KeyError):
        return None


def provision(api: ElevenLabs, client: Client, public_url: str, state_path: Path, voice_id: str | None = None,
              make_secret=lambda: secrets.token_urlsafe(32)) -> VoiceState:
    """Makes the secret and the agent the first time; afterwards only moves the agent to the new public address (a quick
    tunnel has a new one every time). What is kept (the agent, the secret) is in `state_path`, which is git-ignored."""
    state = load_state(state_path)
    if state is None:
        secret = make_secret()
        secret_id = api.create_secret("screening-voice", secret)
        agent_id = api.create_agent(agent_config(client, public_url, secret_id, voice_id))
        state = VoiceState(agent_id, secret_id, secret)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state.__dict__), encoding="utf-8")
    else:
        api.update_agent(state.agent_id, agent_config(client, public_url, state.secret_id, voice_id))
    return state
