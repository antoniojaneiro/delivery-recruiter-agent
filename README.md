# delivery-recruiter-agent

An AI candidate-screening agent for a fictional client, Grupo Sazón, a restaurant chain hiring delivery drivers in Spain and Mexico. Candidates chat with the agent in Spanish or English; recruiters follow them in a dashboard. **The agent screens and summarises; a recruiter makes every hiring decision.**

- **The agent** asks for consent, collects and validates seven screening fields, disqualifies or qualifies, offers a call time, and stores the conversation, the structured JSON and a recruiter summary card in SQLite. The model words the messages in a written personality; code decides everything that matters and checks every message.
- **The recruiter dashboard** (Spanish or English): filter and search candidates, read the card, transcript and audit log, set a hiring status, assign, add notes, work through the review queue of agent rejections, erase a candidate's data, manage call times per country, open or close applications, and see the funnel.
- **A chat in the browser** to try the agent, with a live view of what it has understood.

Design: [docs/PHASE1_PROCESS_DESIGN.md](docs/PHASE1_PROCESS_DESIGN.md). Decisions and open items: [docs/DECISIONS.md](docs/DECISIONS.md). The assignment: [docs/TASK.md](docs/TASK.md).

## Run it

Python **3.12 or newer** and a Gemini API key (free tier, from Google AI Studio).

```
python -m pip install -e ".[dev]"
copy .env.example .env                 # Windows (cp on macOS/Linux); add your GEMINI_API_KEY; never commit .env

python -m sazon.chat                   # terminal chat: /new, /resume <id>, /state, /inbox, /wait24h, /help, /quit
streamlit run apps/chat_app.py         # the chat in the browser (saves to data/demo/chat.db, never the real database)
python -m sazon.accounts add Ana       # create a recruiter account (asks for the password)
streamlit run apps/dashboard.py        # recruiter dashboard, local only; sign in with an account
python -m sazon.reminders --every 600  # the 24-hour reminder job (queues messages for a real channel; see /inbox)
python -m sazon.demo --list            # fictional conversations played on the real agent
python -m sazon.demo --only happy_es   # transcripts go to data/demo/transcripts.md
```

Tests:

```
python -m pytest -q -n 4               # about 1100 offline tests, no network
python -m pytest -m live -q            # real-model checks; needs the key; fictional data; mind the free tier's limits
python -m sazon.chat --list-models     # if the default model name returns 404 (override with LLM_MODEL in .env)
```

The recruiters' database is `data/sazon.db` and the error log `data/sazon.log` (set `SAZON_DB` to use another file for the chat and the dashboard alike). Everything under `data/` is git-ignored.

## How the repo is organised

```
screener/        the engine: screening rules (screening.py, directive.py), the save cycle (conversation.py), wording
                 (phrasing.py, language.py), storage (store*.py), recruiter rules and view, reminders, summary, funnel.
                 Knows no company.
sazon/           Grupo Sazón as a client of the engine
  spec.py          its fields, validators, rules, persona and recruiter texts
  pack.py          its fixed texts, Spanish and English
  ui_pack.py       every word of the dashboard and chat app, Spanish and English
  client.py        service areas, call calendar, reminder clock
  chat.py, reminders.py, accounts.py     the commands above
  demo/            scenarios.py (the fictional conversations) and runner.py
apps/            the Streamlit apps: dashboard.py, chat_app.py and views/ (the dashboard's pages)
docs/            the Phase 1 design, the decision log, the assignment
tests/           engine/ (rules, store, jobs), client/ (Sazón texts, checks and golden snapshot),
                 apps/ (dashboard and chat app), live/ (real model), support/ (fakes, a second client, helpers)
data/            runtime files, git-ignored: sazon.db, sazon.log, demo/ (chat.db, transcripts.md, old_runs/)
.claude/         the skills this repo's workflow uses; see CLAUDE.md
```

The engine never imports `sazon`; a test fails if it does or if it names a client. To serve a similar client, add a package beside `sazon/` with the same pieces: a `ScreeningSpec` (fields, how to read and check each, the rules that end a screening, a persona), a `Pack` (every fixed text, in each language) and a `Client` (service areas, an optional call calendar, the reminder clock). An incomplete spec or client fails when built and lists every problem. `tests/support/toy_spec.py` is a second client (warehouse pickers) that the tests run through the real engine.

## Why this LLM

**Gemini (`gemini-3.5-flash-lite` by default) through its OpenAI-compatible endpoint** (D2, D23, D33). It follows JSON instructions well enough for structured extraction in Spanish and English, it has a free tier with no card, and the OpenAI-style client keeps the model swappable behind one small interface (`screener/llm.py`). The code decides everything that matters (validation, qualified or disqualified, what to collect next, what is stored); the model reads a message into fields and words a short reply. Consent, stop requests, call-time picks and every closing message are read or written by plain code.

- **The free tier is not enough for production.** It allows 15 requests a minute and the client expects about 1000 applications a week; a paid tier with a data-processing agreement is needed.
- **Free-tier prompts may be used by Google to improve its products.** Use fictional candidates only until a paid or EU-compliant tier is chosen. The consent text names the external AI service; it still needs legal review.

## Data and compliance notes

Hiring is high-risk under the EU AI Act (Annex III) and Mexico has its own data law. The design tells the candidate it is an AI and asks for consent first, keeps a human decision-maker, logs every decision with its actor, collects only the screening fields, infers nothing about emotions or personality, and treats candidate text as untrusted. A candidate's data can be erased from the dashboard (it is overwritten, not just deleted); nothing is erased automatically. The login is a prototype measure: a real deployment needs the company's single sign-on. The browser chat has no login and is for your own computer only. This is an engineering baseline, not legal advice.
