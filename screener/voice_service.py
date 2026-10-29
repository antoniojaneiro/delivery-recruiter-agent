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

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from screener import turn
from screener.channel import VOICE
from screener.chat import write_error
from screener.client import Client
from screener.llm import LLM
from screener.run_once import run_once

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


def request_shape(body: dict) -> dict:
    """What a call looked like, with none of what was said: for finding out how ElevenLabs sends a turn (`shapes_log`)."""
    extra = body.get("elevenlabs_extra_body") if isinstance(body, dict) else None
    messages = body.get("messages") if isinstance(body, dict) and isinstance(body.get("messages"), list) else []
    roles = [m.get("role") for m in messages if isinstance(m, dict)]
    session = session_of(body)
    where = None if session is None else ("extra" if isinstance(extra, dict) and extra.get("voice_session") == session else "prompt")
    return {"keys": sorted(body) if isinstance(body, dict) else [], "extra_keys": sorted(extra) if isinstance(extra, dict) else [],
            "roles": roles, "user_turns": roles.count("user"), "session_from": where}


# The call is ended by answering with this tool call, which ElevenLabs offers an agent that has the end_call system tool.
END_CALL = {"id": "call_end", "type": "function",
            "function": {"name": "end_call", "arguments": json.dumps({"reason": "The conversation is finished."})}}


def offers_end_call(body: dict) -> bool:
    """The request lists the end_call tool: only then is the call ended (never a tool the agent does not have)."""
    tools = body.get("tools") if isinstance(body, dict) else None
    return isinstance(tools, list) and any(
        isinstance(tool, dict) and isinstance(tool.get("function"), dict) and tool["function"].get("name") == "end_call"
        for tool in tools)


def _chunk(content: str | None, finish: str | None, completion_id: str, tool_calls: list | None = None) -> str:
    delta = {"tool_calls": tool_calls} if tool_calls else ({} if content is None else {"role": "assistant", "content": content})
    event = {"id": completion_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "screening-engine",
             "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def create_voice_app(client: Client, store, llm: LLM, *, secret: str, clock=datetime.now,
                     log_path: Path | None = None, shapes_log: Path | None = None) -> FastAPI:
    """`shapes_log`: when given, one line per call with its shape (never the words), to see how ElevenLabs sends a turn."""
    app = FastAPI(title="Voice agent brain")
    default_language = client.spec.pack.default_language

    def authorised(authorization: str | None) -> bool:
        scheme, _, token = (authorization or "").partition(" ")
        return scheme == "Bearer" and bool(token) and hmac.compare_digest(token.encode(), secret.encode())

    def apology(candidate_id: str | None) -> str:
        record = store.get(candidate_id) if candidate_id else None
        language = (record.state or {}).get("language") if record else None
        return turn.technical_error_message(client.spec, language or default_language)

    def reply_to(body: dict) -> tuple[str, bool]:
        """What to say, and whether the conversation is over once it is said (then the call is ended)."""
        session = session_of(body)
        said, index = last_said(body)
        candidate_id = store.voice_session_candidate(session, clock()) if session else None
        if candidate_id is None:
            return apology(None), False  # nobody we know: say sorry, run nothing
        if not said:
            return "", False
        message_id = f"voice:{hashlib.sha256(session.encode()).hexdigest()[:16]}:{index}"
        ran = run_once(store, candidate_id, message_id,
                       lambda: turn.handle_message(llm, store, client, candidate_id, said, clock(), VOICE),
                       clock=clock, wait=BUSY_WAIT_SECONDS)  # the turn is saved even if its reply is not: a repeat waits for the claim to go stale
        if ran.status in ("busy", "failed"):  # nothing may reach the candidate's ears but the fixed apology
            if ran.error is not None and not isinstance(ran.error, sqlite3.OperationalError):
                write_error(ran.error, clock(), log_path)
            return apology(candidate_id), False
        return ran.reply, turn.conversation_is_over(store, client, candidate_id)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    @app.post("/{prefix:path}/chat/completions")  # a caller that adds /chat/completions to the address it was given (ElevenLabs does)
    def completions(request: Request, body: dict = Body(...), authorization: str | None = Header(None), prefix: str = ""):
        if not authorised(authorization):
            raise HTTPException(401, "unauthorised")
        if shapes_log is not None:
            with shapes_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**request_shape(body), "path": request.url.path}) + "\n")
        completion_id = "chatcmpl-" + hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:16]
        if body.get("stream", True) is False:
            reply, over = reply_to(body)
            ends = over and offers_end_call(body)
            message = {"role": "assistant", "content": reply, **({"tool_calls": [END_CALL]} if ends else {})}
            return JSONResponse({"id": completion_id, "object": "chat.completion", "created": int(time.time()),
                                 "model": "screening-engine",
                                 "choices": [{"index": 0, "message": message,
                                              "finish_reason": "tool_calls" if ends else "stop"}]})

        def events():
            yield _chunk("", None, completion_id)  # the answer starts at once; the turn runs while this chunk is on its way
            reply, over = reply_to(body)
            if reply:
                yield _chunk(reply, None, completion_id)
            if over and offers_end_call(body):  # the farewell is said first, then the call is ended
                yield _chunk(None, None, completion_id, tool_calls=[{**END_CALL, "index": 0}])
                yield _chunk(None, "tool_calls", completion_id)
            else:
                yield _chunk(None, "stop", completion_id)
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
