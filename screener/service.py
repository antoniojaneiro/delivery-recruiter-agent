"""D75: the HTTP service over the engine. A channel (a web page, WhatsApp, the voice agent) starts a candidate, sends
messages and uploads, and collects the queued messages. The rules stay in the engine; this module only decides who
may call, runs each message id once, applies the rate limit and turns the answers into HTTP.

Handlers are plain functions, so the server runs each in a thread. Nothing is kept in memory between requests: the
token hashes, the stored replies and the rate-limit counts are in the store, so several server processes work."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import anyio.to_thread
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from screener import dialog, slot_offers, turn
from screener.channel import BUTTON
from screener.chat import write_error
from screener.client import Client
from screener.cv import MAX_BYTES as MAX_CV_BYTES
from screener.llm import LLM
from screener.run_once import run_once

MAX_TEXT = 4000  # characters in one message
BUSY_WAIT_SECONDS = 20  # how long a resend waits for the first copy of the same message to finish
FINISH_ATTEMPTS = 5
UPLOAD_SLACK = 64 * 1024  # what a multipart body adds to the file
UPLOAD_PATH = re.compile(r"/candidates/[^/]+/cv")


class _LimitUpload:
    """Stops an upload over the size limit before anyone parses it, whoever sends it: by the declared size, or by
    counting the bytes as they arrive when none is declared. The app is told the caller went away and whatever it
    then answers is replaced by a 413 (it would otherwise turn the failed read into a 400)."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not UPLOAD_PATH.fullmatch(scope["path"]):
            return await self.app(scope, receive, send)
        too_big = JSONResponse({"error": "file too big"}, status_code=413)
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            return await too_big(scope, receive, send)
        seen, exceeded, answered = 0, False, False

        async def counted():
            nonlocal seen, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            seen += len(message.get("body", b"")) if message["type"] == "http.request" else 0
            if seen > self.limit:
                exceeded = True
                return {"type": "http.disconnect"}
            return message

        async def watching(message):
            nonlocal answered
            if not exceeded:
                return await send(message)
            if not answered:
                answered = True
                await too_big(scope, receive, send)

        await self.app(scope, counted, watching)
        if exceeded and not answered:
            await too_big(scope, receive, send)


@dataclass(frozen=True)
class Limits:
    per_minute: int = 20  # a person types, so more than this is a script
    total: int = 300  # one application; a finished chat stores nothing more once it is over this


class MessageIn(BaseModel):
    message_id: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=MAX_TEXT)


class BookIn(BaseModel):
    message_id: str = Field(min_length=1, max_length=100)
    slot_id: int


class AckIn(BaseModel):
    ids: list[int] = Field(max_length=200)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_app(client: Client, store, llm: LLM, *, api_key: str | None = None, limits: Limits = Limits(),
               clock=datetime.now, log_path: Path | None = None, threads: int = 200,
               busy_wait: float = BUSY_WAIT_SECONDS) -> FastAPI:
    """`api_key` is for the trusted channel adapter: it may start candidates and act for any of them. Without it
    anyone may start one. A candidate's own token (from the start call) opens only that candidate."""

    @asynccontextmanager
    async def lifespan(_app):
        anyio.to_thread.current_default_thread_limiter().total_tokens = threads  # the default is 40
        yield

    app = FastAPI(title="Candidate screening service", lifespan=lifespan)
    app.add_middleware(_LimitUpload, limit=MAX_CV_BYTES + UPLOAD_SLACK)

    @app.exception_handler(Exception)
    def unexpected(_request, error):
        """Whatever was not foreseen: logged with an id (never the candidate's words), nothing technical shown (D43)."""
        error_id, _ = write_error(error, clock(), log_path)
        return JSONResponse({"error": "internal", "error_id": error_id}, status_code=500)

    @app.exception_handler(sqlite3.OperationalError)
    def too_busy(_request, error):
        """Writes are one at a time; when the wait for the lock runs out the caller is asked to try again (a resend
        of the same message id is safe), instead of seeing a server error."""
        if "locked" not in str(error) and "busy" not in str(error):
            raise error
        return JSONResponse({"error": "busy, try again"}, status_code=503, headers={"Retry-After": "2"})

    def is_adapter(key: str | None) -> bool:
        return api_key is not None and key is not None and hmac.compare_digest(key, api_key)

    def not_found() -> HTTPException:
        return HTTPException(404, "not found")  # the same answer for a wrong token and an unknown candidate

    def candidate(candidate_id: str, authorization: str | None = Header(None),
                  x_api_key: str | None = Header(None)) -> str:
        if store.get(candidate_id) is None:
            raise not_found()
        if is_adapter(x_api_key):
            return candidate_id
        scheme, _, token = (authorization or "").partition(" ")
        if scheme != "Bearer" or not token or not store.token_matches(candidate_id, _hash(token)):
            raise not_found()
        return candidate_id

    def once(candidate_id: str, message_id: str, work) -> JSONResponse:
        """Runs `work` for a message id exactly once; a resend gets the stored reply."""
        def limited():
            recent, total = store.candidate_message_counts(candidate_id, clock() - timedelta(minutes=1))
            if recent >= limits.per_minute or total >= limits.total:
                return {"Retry-After": "60"} if recent >= limits.per_minute else {}

        ran = run_once(store, candidate_id, message_id, work, clock=clock, wait=busy_wait, before=limited,
                       finish_attempts=FINISH_ATTEMPTS)
        if ran.status == "busy":
            return JSONResponse({"error": "busy"}, status_code=409)
        if ran.status == "refused":
            return JSONResponse({"error": "too many messages"}, status_code=429, headers=ran.refusal)
        if ran.status == "failed":
            if isinstance(ran.error, sqlite3.OperationalError):
                raise ran.error
            error_id, _ = write_error(ran.error, clock(), log_path)
            return JSONResponse({"error": "internal", "error_id": error_id}, status_code=500)
        if ran.status == "unrecorded":
            raise ran.error  # answered "busy"; the claim stays, so a resend waits and the message is not run again
        return JSONResponse({"reply": ran.reply})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/candidates", status_code=201)
    def start(x_api_key: str | None = Header(None)):
        if api_key is not None and not is_adapter(x_api_key):
            raise HTTPException(401, "api key needed")
        candidate_id, reply = dialog.new_candidate(store, client, clock(), BUTTON)
        if store.get(candidate_id) is None:  # applications are closed: nothing was created
            return JSONResponse({"reply": reply}, status_code=503)
        token = secrets.token_urlsafe(32)
        for attempt in range(3):
            try:
                store.set_token(candidate_id, _hash(token))
                break
            except sqlite3.OperationalError:
                if attempt == 2:  # nobody holds a token for this candidate: do not leave an empty one in the dashboard
                    try:
                        store.erase_candidate(candidate_id, "service", clock(), "start failed")
                    except sqlite3.OperationalError:
                        pass
                    raise
                time.sleep(0.1)
        return {"candidate_id": candidate_id, "token": token, "reply": reply}

    @app.post("/candidates/{candidate_id}/messages")
    def message(body: MessageIn, candidate_id: str = Depends(candidate)):
        return once(candidate_id, body.message_id,
                    lambda: turn.handle_message(llm, store, client, candidate_id, body.text, clock()))

    @app.post("/candidates/{candidate_id}/cv")
    def upload(request: Request, file: UploadFile = File(...), message_id: str = Form(min_length=1, max_length=100),
               candidate_id: str = Depends(candidate)):
        if client.spec.pack.cv is None:
            raise not_found()
        data = file.file.read(MAX_CV_BYTES + 1)
        if len(data) > MAX_CV_BYTES:
            return JSONResponse({"error": "file too big"}, status_code=413)
        return once(candidate_id, message_id, lambda: turn.handle_cv(llm, store, client, candidate_id, data, clock()))

    @app.get("/candidates/{candidate_id}/times")
    def times(candidate_id: str = Depends(candidate), month: str | None = None, day: str | None = None):
        """For the picker: `month=YYYY-MM` gives the days with free times, `day=YYYY-MM-DD` that day's times. Only the
        times of the candidate's own country are shown."""
        country = slot_offers.country_of(store, client, candidate_id) if slot_offers.may_choose_time(store, client, candidate_id) else None
        try:
            if month is not None:
                first = date.fromisoformat(month + "-01")
                days = store.free_days(country, first, clock()) if country else {}
                return {"days": {d.isoformat(): n for d, n in days.items()}}
            if day is not None:
                found = store.free_slots_on(country, date.fromisoformat(day), clock()) if country else []
                return {"times": [{"id": s.id, "label": f"{s.starts_at:%H:%M}"} for s in found]}
        except ValueError:
            raise HTTPException(422, "a month is YYYY-MM and a day is YYYY-MM-DD") from None
        raise HTTPException(422, "give a month or a day")

    @app.post("/candidates/{candidate_id}/book")
    def book(body: BookIn, candidate_id: str = Depends(candidate)):
        """A time chosen in the picker: the answer typing its number would give."""
        return once(candidate_id, body.message_id,
                    lambda: turn.handle_slot(store, client, candidate_id, body.slot_id, clock()))

    @app.get("/candidates/{candidate_id}/outbox")
    def outbox(candidate_id: str = Depends(candidate)):
        return {"messages": [{"id": e.id, "text": e.text} for e in store.outbox_pending(candidate_id)]}

    @app.post("/candidates/{candidate_id}/outbox/ack")
    def acknowledge(body: AckIn, candidate_id: str = Depends(candidate)):
        own = {e.id for e in store.outbox_pending(candidate_id)}
        for entry_id in body.ids:
            if entry_id in own:
                store.mark_delivered(entry_id, clock())
        return {"status": "ok"}

    return app
