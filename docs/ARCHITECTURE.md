# Architecture

How the screening agent is built and why it is laid out this way. For the process the agent follows, read [PHASE1_PROCESS_DESIGN.md](PHASE1_PROCESS_DESIGN.md); for every decision and the options that were weighed, [DECISIONS.md](DECISIONS.md) (the D-numbers in the code point there).

## The idea in one paragraph

A language model is good at reading a messy message ("tengo 2 años con Glovo y empiezo ya") and at wording a friendly reply, and bad at being the thing that decides who is qualified. So the split is strict: **the model only reads a message into fields and words a short reply; plain, tested code decides everything else**: what to ask next, whether a value is valid, whether the candidate qualifies, which call times are free, and whether a model-written message may be sent at all. If the model is slow, down or wrong, the conversation falls back to fixed texts and never crashes. A recruiter makes every hiring decision.

## Layers

```
 candidate ── terminal chat │ browser chat │ HTTP service │ voice call ───────────────┐
                                                                                      ▼
                                       turn.py   one message in, one reply out
                                          │
        extraction.py ◄── the model reads ┤  Screening (screening*.py): the rules, as state that is saved
        phrasing.py   ◄── the model words ┤  directive.py: WHAT to say (data), phrasing.py: HOW it is said
                                          │  slot_offers / spoken_booking: call times
                                          ▼
                       conversation.py   load → change → save (versioned, retried on a lost race)
                                          ▼
                       store*.py (SQLite)   candidates, messages, events, calls, recruiters
                                          ▲
 recruiter ── dashboard (Streamlit) ──────┘  reads and writes through the same store and the same rules
```

## Repository map

```
screener/    the engine; knows no company and never imports sazon/
  turn.py, conversation.py, session.py     one message in, one reply out; the save cycle
  screening*.py, directive.py, spec.py     the rules as state; what to say; what a client must define
  extraction.py, phrasing.py, llm.py, gemini.py     the model: read a message, word a reply, behind one small interface
  consent.py, language.py, validators.py, cv.py     plain-code readers: consent, language, values, the optional PDF CV
  channel.py                               text, button or voice: how times are offered and who words the reply
  slot_offers.py, spoken_booking.py, spoken_when.py, slot_choice.py, slot_calendar.py     offering and booking a call
  recruiter_calls.py, recruiter_rules.py, call_times.py, recruiters.py, login.py     recruiters, their hours, calls, sign-in
  store.py, store_db.py, store_schema.py, store_service.py, store_types.py     SQLite, in parts
  summary.py, inspector.py, funnel.py, pipeline.py, recruiter_view.py     what recruiters see, built by code
  service.py, run_once.py                  the HTTP service; "run a message exactly once"
  reminders.py                             the 24-hour reminder job
  voice_service.py, voice_agent.py, voice_call.py, launching.py     live voice: endpoint, ElevenLabs agent, call state
sazon/       Grupo Sazón as a client of the engine
  spec.py, fields.py, validators.py        its seven fields, checks, rules and persona
  pack.py, ui_pack.py                      every fixed text and every screen word, Spanish and English
  client.py, areas.py, config.py           service areas and the call calendar; paths and environment
  chat.py, server.py, reminders.py, voice_*   the entry points
  demo/                                    scripted conversations (scenarios, runner) and the demo database (seed)
apps/        the Streamlit apps: dashboard.py (+ views/), chat_app.py
docs/        this folder
tests/       engine/ client/ apps/ load/ live/ and support/
data/        runtime files, git-ignored: sazon.db, sazon.log, voice.json
```

### Engine and client

`screener/` is the reusable part; `sazon/` is one company using it. A client is three things:

- a `ScreeningSpec`: its fields, how to read and check each, the rules that end a screening, a persona, the recruiter's labels;
- a `Pack`: every fixed text, in each language;
- a `Client`: service areas, an optional call calendar, the reminder clock.

An incomplete spec or client fails when built and lists every problem. `tests/engine/test_engine_boundary.py` fails if the engine imports or even names the client, and `tests/support/toy_spec.py` is a second client (warehouse pickers) that the tests run through the real engine, so the split is checked, not assumed.

## One message, step by step

1. **A channel hands over a message**: the terminal, the browser chat, the HTTP service or a voice call. Each channel is a small `Channel` value (text, button, voice) that says how call times are offered, whether the model words the reply and whether a file can be sent.
2. **`turn.handle_message`** loads the candidate's saved state (`conversation.run`), and asks the `Screening` what to do.
3. **Plain code goes first**: consent, a request to stop, a call-time pick and the language are read without the model. Candidate text is untrusted: it is fenced as data, capped in length, stripped of the tags that fence it, and never obeyed.
4. **The model reads** the rest into the client's fields as typed JSON (`extraction.py`). Each value is then checked in code; an invalid or unclear value is asked again, with an example, up to five times.
5. **The `Screening` decides** (`screening.py`, `screening_precedence.py`): a `Directive` such as "ask the city", "confirm a no-license", "offer call times" or "close as qualified". A directive is data: it says *what* to say, never the words.
6. **`phrasing.py` words it.** The model may word a question or a confirmation in the client's persona; code checks the result (length, one question, right language, no pay or time promised) and sends a fixed text if a check fails or the model is down. Closings, consent and call times are always fixed text.
7. **The turn is saved** as one versioned write (messages, events, extracted values, outcome). A candidate who writes twice at once cannot be lost: the second write is retried against the fresh copy.

The conversation state, the extracted JSON and the recruiter's summary are three separate things: the state lives in the candidate row, the JSON holds only validated values, and the summary card is built by code from them (`summary.py`), never by the model.

## Booking a call

A candidate who qualifies books a 15-minute call themselves: a calendar button in the browser chat, a numbered list in text, or day-then-time by voice (below). Times come from recruiters' weekly hours and days off, per country and in that country's time zone; a candidate books from tomorrow up to four weeks ahead. Booking is one atomic step in the store, so two candidates can never take the same time, and many candidates choosing the same minute are spread over the recruiters free then.

Recruiters work on the same calls from the dashboard's calendar: book or move a call for a candidate (the chat is told in a fixed text), make a time for a candidate, set hours and days off, or leave. Calls that no longer fit are handed to another recruiter free at the same time, or released with the candidate told and shown the free times (`recruiter_calls.py`). Who may be given a call is one pure answer with a reason (`recruiter_rules.may_schedule`, `may_choose`).

## Live voice (bonus)

```
 browser ──mic──► ElevenLabs (listens, speaks, takes turns) ──► our endpoint ──► the same engine
 "Talk to Sofía"   private agent, signed address                 voice_service.py    turn.handle_message(channel=VOICE)
```

ElevenLabs only does the audio. For every turn it calls our own endpoint (an OpenAI-style chat-completions call), so the disclosure, the rules and the booking are the engine's, word for word, and no second AI decides what to say. The endpoint checks a shared secret and a short-lived voice session made by the chat page, runs each turn exactly once, answers at once and ends the call itself when there is nothing more to say. No audio is kept. A voice turn makes one model call to read the answer (retried once if the reply cannot be parsed), with a 5-second budget and no SDK retries; a failure is spoken as "I couldn't hear you, could you repeat please?". `python -m sazon.voice_launch` opens a tunnel to the endpoint only, creates the agent and starts it. The browser side is a small file, [`sazon/voice_call.js`](../sazon/voice_call.js), tested in Node.

## Data

SQLite, one file (`data/sazon.db`), in parts that share one connection layer: candidates and messages, events (every decision with its actor), recruiter status and notes, calls and recruiters, and what the HTTP service keeps (per-candidate token hash, the reply to each message id so a resend is answered once). Erasing a candidate deletes and overwrites every row and keeps only an anonymous audit line. Nothing is deleted automatically.

## Recruiter dashboard

A Streamlit app (`apps/dashboard.py`, pages in `apps/views/`) over the same store and rules: the candidate table (filter, search, one Estado per candidate), a candidate's card, transcript and audit log, a review queue of the agent's rejections, a call-times calendar, the funnel, and the hiring manager's page to create recruiters. What a screen decides is plain code in `screener/recruiter_view.py` and `recruiter_rules.py`, testable without Streamlit. Every word on screen comes from `sazon/ui_pack.py` in Spanish and English.

## Safety and compliance in code

| Concern | Where it is handled |
| --- | --- |
| Tell the candidate it is an AI, ask consent first | A fixed first message; nothing is stored or sent to the model before a yes (`consent.py`). |
| A person decides | The agent only screens; a recruiter sets hired or rejected and can overrule any state. A "no" on license or area is confirmed once, so one misread never rejects anyone. |
| Prompt injection | Candidate text and CV text are data: fenced, capped, never obeyed; model wording is checked and replaced by a fixed text if it fails. |
| Log decisions | Every decision is an event with its actor. |
| Minimise and erase | Only the screening fields are collected; erasure overwrites. No emotion or personality inference, by text or voice. |
| Failures | A model failure sends a fixed apology and is logged with an id, never the candidate's words; an error never ends the chat. |

## Tests

About 1,200 offline tests, no network (`pytest -n 4`). `engine/` (rules, store, jobs, service), `client/` (Sazón's texts, a golden snapshot of every fixed text, the demo seed), `apps/` (Streamlit through `AppTest`, plus the call page's JavaScript in Node), `load/` (a busy day, 200 candidates against a real server with a slow failing fake model), `live/` (the real model, opt-in) and `support/` (fakes, helpers, the second client). Pure rules are tested as tables of inputs and expected outputs (`tests/support/tables.py`).
