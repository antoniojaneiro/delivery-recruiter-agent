"""The page that holds a live voice call inside the chat (D93). It is a small piece of HTML and JavaScript: the browser asks for the
microphone, connects to ElevenLabs with the signed address our server asked for, and shows whether Sofía is listening or
speaking. The conversation itself is saved by the engine through the voice endpoint, so the chat shows it as messages.

The values put into the page (the address and the session) are written as JSON, so nothing in them can end the script. The
ElevenLabs API key is never here: only the signed address, which is valid for one start within 15 minutes."""
import json
from pathlib import Path

# Floating on purpose while this is tried locally; pin or copy the SDK into the project before a real deployment.
SCRIPT = (Path(__file__).parent / "voice_call.js").read_text(encoding="utf-8")  # the browser side; run in Node by the tests
SDK = "https://esm.sh/@elevenlabs/client"

_WORDS = {
    "es": {"connecting": "Conectando…", "listening": "Escuchando…", "speaking": "Sofía está hablando…",
           "ended": "Llamada terminada.", "mic": "No se pudo usar el micrófono. Permite el acceso y vuelve a pulsar «Hablar con Sofía».",
           "error": "Hubo un problema con la llamada."},
    "en": {"connecting": "Connecting…", "listening": "Listening…", "speaking": "Sofía is speaking…",
           "ended": "Call ended.", "mic": "The microphone could not be used. Allow access and press “Talk to Sofía” again.",
           "error": "There was a problem with the call."},
}


def _json(value) -> str:
    """JSON that is safe inside a script tag: no `</script>` and no HTML comment can come out of it."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def call_html(signed_url: str, session: str, language: str, opening: str, agent_language: str | None) -> str:
    """`language`: the one of the screen. `opening`: the first words of the call (the engine's). `agent_language`: the language
    the candidate writes in, so the call starts in it (None: the agent's own)."""
    words = _WORDS.get(language, _WORDS["es"])
    call = {"words": words, "session": session, "signedUrl": signed_url, "opening": opening, "language": agent_language}
    return f"""<div id="status" style="font-family:sans-serif;font-size:15px;padding:8px 0">{words['connecting']}</div>
<script type="module">
import {{ Conversation }} from {_json(SDK)};
{SCRIPT}
startCall({_json(call)}, {{ Conversation, status: document.getElementById("status"), mic: navigator.mediaDevices, parent: window.parent }});
</script>"""
