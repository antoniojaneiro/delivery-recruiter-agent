# Hand-over: what Grupo Sazón must decide or provide

What is built, what is still needed from the client, and how to start each part. Not legal advice.

## Start it

Every command, the demo data and the configuration are in [RUNNING.md](RUNNING.md). Keep the dashboard and the chat on your own computer until the login is replaced (below).

## The client must provide

| Item | Why it matters | Where it goes |
| --- | --- | --- |
| The real service areas (cities and nearby towns, per country) | The list in the code is a sample; candidates are accepted or rejected by it. | `sazon/areas.py` |
| Recruiters, their country and their hours | Call times come from recruiters' availability: the hiring manager creates them (Recruiters page); by default each works Monday to Friday, 9:00 to 17:00 in their country, and changes it in the Calendar page. The hiring manager takes calls too (`HIRING_MANAGER_COUNTRY` in `.env`, Spain if empty; D89). | Dashboard (D80, D82) |
| A paid model plan with a data-processing agreement | The free tier allows 15 requests a minute, may train on prompts, and cannot serve about 1000 applications a week. | `.env` (`GEMINI_API_KEY`, `LLM_MODEL`) |
| Single sign-on for recruiters | The built-in login (email and password, recruiters created by the hiring manager from `.env`) is a prototype; keep the dashboard local until it is replaced. | Dashboard login (D80) |
| An ElevenLabs account for live voice, with a data-processing agreement | Audio is heard and transcribed by ElevenLabs. Locally it is tried with your own key; a deployment needs the client's account, a stable HTTPS address for the voice endpoint and their approval. | `.env` (`ELEVENLABS_API_KEY`), `python -m sazon.voice_launch` (D93) |
| A messaging channel (WhatsApp or similar) | Today candidates use the terminal or the test chat. The service is ready for an adapter. | `screener/service.py` (D75) |

## The client's lawyers must approve

The list below says *what* needs approval. A separate document with each text word for word, and sample conversations, is still to be written (the texts are in `sazon/pack.py`).

1. The AI disclosure and consent question (names Sofía; Spanish and English). The consent record stores a fingerprint of the exact text shown.
2. Every farewell, and the qualified message and the "write to us when you want to book" texts (the 48-hour promise is gone, D81).
3. The CV upload notice and the read-back of what was taken from a CV.
4. How long answers, transcripts, error logs and uploaded CVs may be kept. Today nothing is deleted automatically; erasure is on request from the dashboard.
5. The messages a candidate gets when a recruiter books or moves their call, and when their call is no longer available and they can pick again (`scheduled`, `moved`, `cancelled`, `later` in `sazon/pack.py`), and the four "use the button" offers for the browser chat (`offer_button`, D90).
6. Approved answers about pay.
7. A sample of real conversations. The model's wording varies, so the fixed texts are not the whole picture.
8. Live voice (D93): the nine spoken question texts (`voice` in `sazon/pack.py`, Spanish and English), that the call opens with the same AI disclosure and consent question, and that the audio is heard and transcribed by ElevenLabs as a processor (the agent keeps no recording and one day of history; no analysis, no emotion inference).

`python -m sazon.demo.seed` fills a database with fictional candidates to look at; `python -m sazon.demo --list` shows the scripted conversations that can be played on the real model.

## Known limits

- Live voice was tried in real calls with ElevenLabs on a free account and a quick tunnel; a deployment needs a stable HTTPS address, the client's ElevenLabs account and agreement, and pinning the browser SDK (D93, DECISIONS section 9).
- The real model was not load-tested (free tier). The service and database were, with a fake model, at about 25 times the expected peak (D75).
- A rejected candidate cannot reopen the chat; a recruiter can set a status.
- One database file on one machine: no backup or failover.
- A third language needs engine edits (word lists, day names, the extraction prompt).
- Call times are 15 minutes, from each recruiter's weekly hours. A candidate books from tomorrow up to four weeks ahead (never the same day); a recruiter may book any time that has not started. A recruiter's country is fixed when the manager creates them (D87).
- Erasing a candidate from the dashboard deletes and overwrites their rows, but readable copies of earlier row versions can stay in the database file until it is rewritten (`VACUUM`); see DECISIONS, section 9.
- Streamlit's own text in the CV uploader ("Upload", "2MB per file") follows the candidate's browser language, not the page's switch.
- A link to a candidate (`?candidate=ID`) does not survive the dashboard's login page.
