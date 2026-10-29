"""D93: the endpoint a live voice agent calls for every spoken turn. ElevenLabs does the listening and the speaking; for each turn
it makes an OpenAI-style chat completions call to this app, and the words it gets back are the words it speaks. So the engine
is the agent's brain: the fixed texts, the rules and the booking are the same as in the text chat, with the spoken channel
(`voice=True`).

Kept apart from the candidates' service on purpose: it is the only part that has to be reachable from outside while we run
locally, so it opens nothing else. It believes a call only when it carries the shared secret and a live voice session (made
for one candidate by our own page), takes only the last thing the candidate said and ignores the history it is sent, and
runs a turn once even if the call is repeated. Whatever goes wrong is spoken as the fixed apology, never a server error."""
import hashlib
import hmac
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from screener import turn
from screener.chat import write_error
from screener.client import Client
from screener.llm import LLM

BUSY_WAIT_SECONDS = 8  # how long a repeated call waits for the first copy of the same turn
_SESSION_IN_PROMPT = re.compile(r"voice_session=([A-Za-z0-9_-]+)")


def session_of(body: dict) -> str | None:
    """Which voice session a call belongs to: the one place that knows. ElevenLabs may carry it as extra body data or, as a
    dynamic variable, written into the system prompt; either works."""
    extra = body.get("elevenlabs_extra_body") if isinstance(body, dict) else None
    if isinstance(extra, dict) and isinstance(extra.get("voice_session"), str) and extra["voice_session"]:
        return extra["voice_session"]
    messages = body.get("messages") if isinstance(body, dict) else None
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system" and isinstance(message.get("content"), str):
                if found := _SESSION_IN_PROMPT.search(message["content"]):
                    return found[1]
    return None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # OpenAI's parts: [{"type": "text", "text": "..."}]
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    return ""


def last_said(body: dict) -> tuple[str, int]:
    """The last thing the candidate said and which turn it is (how many times they have spoken). The history is ignored."""
    messages = body.get("messages") if isinstance(body, dict) else None
    said = [_text(m.get("content")) for m in messages if isinstance(m, dict) and m.get("role") == "user"] \
        if isinstance(messages, list) else []
    return (said[-1].strip(), len(said)) if said else ("", 0)


def _chunk(content: str | None, finish: str | None, completion_id: str) -> str:
    delta = {} if content is None else {"role": "assistant", "content": content}
    event = {"id": completion_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "screening-engine",
             "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def create_voice_app(client: Client, store, llm: LLM, *, secret: str, clock=datetime.now,
                     log_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Voice agent brain")
    default_language = client.spec.pack.default_language

    def authorised(authorization: str | None) -> bool:
        scheme, _, token = (authorization or "").partition(" ")
        return scheme == "Bearer" and bool(token) and hmac.compare_digest(token.encode(), secret.encode())

    def apology(candidate_id: str | None) -> str:
        record = store.get(candidate_id) if candidate_id else None
        language = (record.state or {}).get("language") if record else None
        return turn.technical_error_message(client.spec, language or default_language)

    def reply_to(body: dict) -> str:
        session = session_of(body)
        said, index = last_said(body)
        candidate_id = store.voice_session_candidate(session, clock()) if session else None
        if candidate_id is None:
            return apology(None)  # nobody we know: say sorry, run nothing
        if not said:
            return ""
        message_id = f"voice:{hashlib.sha256(session.encode()).hexdigest()[:16]}:{index}"
        deadline = time.monotonic() + BUSY_WAIT_SECONDS
        while True:
            claim = store.claim_message(candidate_id, message_id, clock())
            if claim.state == "done":
                return claim.reply
            if claim.state == "new":
                break
            if time.monotonic() > deadline:
                return apology(candidate_id)
            time.sleep(0.05)
        try:
            reply = turn.handle_message(llm, store, client, candidate_id, said, clock(), voice=True)
        except Exception as error:  # noqa: BLE001  nothing may reach the candidate's ears but the fixed apology
            try:
                store.release_message(candidate_id, message_id)
            except sqlite3.OperationalError:
                pass
            if not isinstance(error, sqlite3.OperationalError):
                write_error(error, clock(), log_path)
            return apology(candidate_id)
        try:
            store.finish_message(candidate_id, message_id, reply)
        except sqlite3.OperationalError:
            pass  # the turn is saved; a repeat of this call waits for the claim to go stale rather than run it again
        return reply

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    def completions(body: dict = Body(...), authorization: str | None = Header(None)):
        if not authorised(authorization):
            raise HTTPException(401, "unauthorised")
        reply = reply_to(body)
        completion_id = "chatcmpl-" + hashlib.sha256(f"{time.time()}{reply}".encode()).hexdigest()[:16]
        if body.get("stream", True) is False:
            return JSONResponse({"id": completion_id, "object": "chat.completion", "created": int(time.time()),
                                 "model": "screening-engine",
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                                              "finish_reason": "stop"}]})

        def events():
            yield _chunk("", None, completion_id)  # the role first, as the real API does
            if reply:
                yield _chunk(reply, None, completion_id)
            yield _chunk(None, "stop", completion_id)
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
