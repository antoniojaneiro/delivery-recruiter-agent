# delivery-recruiter-agent

An AI-powered candidate screening agent for a fictional client, Grupo Sazón, a restaurant chain hiring delivery
drivers in Spain and Mexico. Candidates chat with the agent (Spanish or English); recruiters follow them in a
dashboard. **The agent screens and summarises; a recruiter makes every hiring decision.**

- **Chat agent** (`python -m sazon.chat`): asks for consent, collects and validates the seven screening fields,
  disqualifies or qualifies, offers a call slot, and stores the conversation, the structured JSON and a Spanish
  summary card in SQLite.
- **Recruiter dashboard** (`streamlit run dashboard.py`, one login per recruiter): filter and search
  candidates, read the summary, transcript and audit log, set a hiring status, assign, add notes, work through the
  review queue of agent rejections, erase a candidate's data, manage call slots per country, open or close
  applications, and see the funnel.

## Requirements

Python **3.12 or newer**. A Gemini API key (free tier, from Google AI Studio) for the chat and the real-model tests.

## Run it

```
python -m pip install -e ".[dev]"
copy .env.example .env      # Windows (use cp on macOS/Linux), then add your GEMINI_API_KEY; never commit .env
python -m sazon.chat        # terminal chat; commands: /new, /resume <id>, /state, /inbox, /wait24h, /help, /quit
python -m sazon.accounts add Ana     # create a recruiter account (asks for the password); the dashboard needs one
streamlit run dashboard.py  # recruiter dashboard (local only; sign in with an account)
python -m sazon.reminders --every 600   # the 24-hour reminder job (queues messages for the real channel; see /inbox)
python -m sazon.retention [--apply]     # list (or erase) rejected/withdrawn/off-topic candidates older than 6 months
python -m sazon.demo --list # fictional scenarios played on the real agent; transcripts go to data/demo_transcripts.md
python -m pytest -q         # unit tests, no network (the live tests are skipped)
python -m pytest -m live -q # real-model checks; needs the key; fictional data only
python -m sazon.chat --list-models   # if the default model name returns 404 (override with LLM_MODEL in .env)
```

Errors are logged to `data/sazon.log` and the database lives in `data/sazon.db` (both git-ignored; set `SAZON_DB`
to use another file for the chat and the dashboard alike).

## Why this LLM

**Gemini (`gemini-3.5-flash-lite` by default), reached through its OpenAI-compatible endpoint** (D2, D23, D33).
It follows JSON instructions well enough for structured extraction in Spanish and English, it has a free tier with
no card, and the OpenAI-style client keeps the model swappable behind one small interface (`sazon/llm.py`).
The code decides everything that matters (validation, qualified or disqualified, what to ask next, what is
stored); the model only reads a message into fields and phrases a short question. Consent, refusals, stop requests,
slot picks and every closing message are read or written by plain code, never by the model.

Trade-offs to know about:

- **The free tier is not enough for production.** It allows only a handful of requests per minute, and the client
  expects about 1000 applications a week. A paid tier (with a data-processing agreement) is needed.
- **Free-tier prompts may be used by Google to improve its products.** Use only fictional candidates until a paid or
  EU-compliant tier is chosen. After consent, every candidate message is sent to the model. The consent wording now
  names the external AI service (D51); it still needs legal review before real use.

## Data and compliance notes

Hiring is high-risk under the EU AI Act (Annex III) and Mexico has its own data law. The design therefore tells the
candidate it is an AI and asks for consent first, keeps a human decision-maker, logs every decision with its actor,
collects only the screening fields, infers nothing about emotions or personality, and treats candidate text as
untrusted. Candidates can be erased on request from the dashboard (the data is overwritten, not just deleted) and
`sazon.retention` erases rejected candidates after six months (a default to confirm with legal). The consent text
names the external AI service. The login is a prototype measure: a real deployment needs the company's single
sign-on. This is an engineering baseline, not legal advice.

Design: [PHASE1_PROCESS_DESIGN.md](PHASE1_PROCESS_DESIGN.md). Decisions and open items: [DECISIONS.md](DECISIONS.md).
