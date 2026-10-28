# Hand-over: what Grupo Sazón must decide or provide

What is built, what is still needed from the client, and how to start each part. Not legal advice.

## Start it

| What | Command | Notes |
| --- | --- | --- |
| Both apps | `python demo_launch.py` | Chat on port 8501, dashboard on 8502. Create the first recruiter account on the dashboard's login page. |
| Candidate service for a channel | `python -m sazon.server` | Needs `SAZON_API_KEY` in `.env`. Port 8000. Put it behind HTTPS. |
| 24-hour reminders | `python -m sazon.reminders --every 600` | Someone must keep it running. Its messages wait in the outbox until a channel sends them. |
| Tests | `python -m pytest -q -n 4` | `-m load` runs the busy-day test, `-m live` the real-model checks (needs the key). |

Keep the dashboard and the chat on your own computer until the login is replaced (below).

## The client must provide

| Item | Why it matters | Where it goes |
| --- | --- | --- |
| The real service areas (cities and nearby towns, per country) | The list in the code is a sample; candidates are accepted or rejected by it. | `sazon/config.py` |
| Call times and who answers calls | The agent offers real times only if recruiters add them. | Dashboard, Horarios |
| A paid model plan with a data-processing agreement | The free tier allows 15 requests a minute, may train on prompts, and cannot serve about 1000 applications a week. | `.env` (`GEMINI_API_KEY`, `LLM_MODEL`) |
| Single sign-on for recruiters | The built-in login is a prototype and anyone who can reach the page can create an account. | Dashboard login (D57, D74) |
| A messaging channel (WhatsApp or similar) | Today candidates use the terminal or the test chat. The service is ready for an adapter. | `screener/service.py` (D75) |

## The client's lawyers must approve

The list below says *what* needs approval. A separate document with each text word for word, and sample conversations, is still to be written (the texts are in `sazon/pack.py`).

1. The AI disclosure and consent question (names Sofía; Spanish and English). The consent record stores a fingerprint of the exact text shown.
2. Every farewell and the "a recruiter will reply within 48 hours" promise, which nothing enforces yet.
3. The CV upload notice and the read-back of what was taken from a CV.
4. How long answers, transcripts, error logs and uploaded CVs may be kept. Today nothing is deleted automatically; erasure is on request from the dashboard.
5. Approved answers about pay.
6. A sample of real conversations. The model's wording varies, so the fixed texts are not the whole picture.

`python -m sazon.demo --list` shows the fictional conversations; `python -m sazon.demo` (or `--only NAME`) plays them on the real model.

## Known limits

- The real model was not load-tested (free tier). The service and database were, with a fake model, at about 25 times the expected peak (D75).
- A rejected candidate cannot reopen the chat; a recruiter can set a status.
- One database file on one machine: no backup or failover.
- A third language needs engine edits (word lists, day names, the extraction prompt).
- The agent always offers the earliest three free call times, so many qualified candidates at once compete for the same ones (D48).
- Streamlit's own text in the CV uploader ("Upload", "2MB per file") follows the candidate's browser language, not the page's switch.
- A link to a candidate (`?candidate=ID`) does not survive the dashboard's login page.
