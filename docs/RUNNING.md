# Running it

Everything needed to install, fill with demo data, run each part and test. Python **3.12 or newer**.

## Install

```
python -m pip install -e ".[dev]"      # ".[service]" is enough to run only the HTTP service
copy .env.example .env                 # Windows (cp on macOS/Linux); never commit .env
```

Put your own values in `.env` (the file only names them):

| Variable | For |
| --- | --- |
| `GEMINI_API_KEY` | The model (free tier, from Google AI Studio). Not needed to browse the demo data or run the tests. |
| `HIRING_MANAGER_EMAIL`, `HIRING_MANAGER_PASSWORD` | The hiring manager signs in to the dashboard with these and creates the recruiters. `HIRING_MANAGER_COUNTRY` (ES or MX) is where the manager takes calls. |
| `ELEVENLABS_API_KEY` | Live voice only. `ELEVENLABS_VOICE_ID` is optional (it must be a voice in your own ElevenLabs account). |
| `SAZON_API_KEY` | The HTTP service only. |
| `LLM_MODEL`, `SAZON_DB`, `SAZON_CHAT_URL`, `SAZON_DASHBOARD_URL` | Optional overrides. `python -m sazon.chat --list-models` helps if the default model name returns 404. |

## See it in two minutes: the demo data

```
python -m sazon.demo.seed --reset      # 27 fictional candidates, 4 recruiters, calls, statuses, notes (no model, no network)
python demo_launch.py                  # chat on :8501, dashboard on :8502; Ctrl+C stops both
```

Sign in to the dashboard (`http://localhost:8502`) as the hiring manager from `.env`, or as a seeded recruiter: `ana@sazon.test` or `miguel@sazon.test` (Spain), `lucia@sazon.test` or `roberto@sazon.test` (Mexico), password `demo-sazon-2026`. The seed refuses a database that already has candidates; `--reset` deletes it first (stop the chat and the dashboard before, or the file is in use). Dates are relative to the moment you seed, so run `--reset` again on the day of the demo. Everything under `data/` is git-ignored.

Then open the chat, write as a candidate (Spanish or English; this part needs the Gemini key), and watch the candidate appear in the dashboard. Erase your test candidates there when done.

## The parts

| What | Command | Notes |
| --- | --- | --- |
| Browser chat | `streamlit run apps/chat_app.py` | Saves to the recruiters' database, so its candidates appear in the dashboard. No login: your own computer only. |
| Recruiter dashboard | `streamlit run apps/dashboard.py` | Local only; prototype login (email and password). |
| Both, joined | `python demo_launch.py` | Each app has a button to the other. |
| Terminal chat | `python -m sazon.chat` | `/new`, `/resume <id>`, `/cv <pdf>`, `/state`, `/inbox`, `/wait24h`, `/help`, `/quit`. |
| HTTP service | `python -m sazon.server` | For a real channel (WhatsApp or similar). Needs `SAZON_API_KEY`; port 8000; put it behind HTTPS. |
| 24-hour reminders | `python -m sazon.reminders --every 600` | Queues messages in the outbox for a channel to send. Someone must keep it running. |
| Live voice | `python -m sazon.voice_launch` | Needs `ELEVENLABS_API_KEY` and `cloudflared` (a free tunnel, no account). Starts a tunnel to the voice endpoint, makes the ElevenLabs agent and runs the endpoint on port 8010; then press "Talk to Sofía" in the chat. `VOICE_LOG_SHAPES=1` logs the shape of each call, never the words. |
| Demo conversations | `python -m sazon.demo --list`, `--only happy_es` | Fictional conversations played on the real model (needs the key); transcripts go to `data/demo/transcripts.md`. |

Runtime files: the database `data/sazon.db`, the error log `data/sazon.log`, the voice agent's id and secret `data/voice.json` (no API key in it).

## Test

```
python -m pytest -q -n 4               # about 1,200 offline tests, no network, a few minutes
python -m pytest -m load -q -s         # a busy day against a real server: 200 candidates, about 11 minutes
python -m pytest -m live -q            # the real model; needs the key; fictional data; mind the free tier's limits
```

The call page's JavaScript is tested in Node; those tests are skipped when Node is not installed.

## The model and its limits

Gemini (`gemini-3.5-flash-lite` by default) through its OpenAI-compatible endpoint (D2): it follows JSON instructions well enough for extraction in Spanish and English, the free tier needs no card, and the model sits behind one small interface (`screener/llm.py`) so it can be swapped. **The free tier is not enough for production** (15 requests a minute against about 1,000 applications a week) and **may use prompts to improve Google's products**, so use fictional candidates only until a paid, data-processing-agreement tier is chosen.
