# Grupo Sazón: candidate screening agent

A conversational agent that screens delivery-driver applicants for **Grupo Sazón** (a fictional restaurant chain hiring in Spain and Mexico), so recruiters only speak to people who qualify. Candidates chat in Spanish or English, or talk to Sofía by voice; recruiters follow everyone in a dashboard. **The agent screens and summarises; a recruiter makes every hiring decision.**

The design rule: the language model only reads a message and words a short reply. Plain, tested code decides everything that matters (what to ask, what is valid, who qualifies, which call times are free), and falls back to fixed texts if the model fails.

## What is in it

- **The agent**: consent and an AI disclosure first, seven validated screening fields (optionally read from a PDF CV), a qualified or disqualified outcome, and the candidate books their own 15-minute call. Conversation, structured JSON and a recruiter summary card are kept separately in SQLite.
- **The recruiter dashboard** (Streamlit, Spanish and English): candidates and their status, card, transcript and audit log, a review queue, a call-times calendar per country, the funnel, erasure of a candidate's data.
- **A browser chat** to try the agent, a **live voice agent** (ElevenLabs does the audio, our engine is the brain), an **HTTP service** for a real channel, and a **24-hour reminder job**.

## Try it

```
python -m pip install -e ".[dev]"
copy .env.example .env                 # add your own keys; see docs/RUNNING.md
python -m sazon.demo.seed --reset      # 27 fictional candidates, recruiters, calls, notes
python demo_launch.py                  # chat on :8501, dashboard on :8502
```

Demo logins and every other command (service, voice, reminders, tests): [docs/RUNNING.md](docs/RUNNING.md).

## The assignment

| Asked for | Where |
| --- | --- |
| Phase 1: process design, 1 to 2 pages | [docs/PHASE1_PROCESS_DESIGN.md](docs/PHASE1_PROCESS_DESIGN.md) |
| Phase 2: a conversational agent in Python that validates, saves JSON and a summary | `screener/` (engine) and `sazon/` (Grupo Sazón) |
| A tool for recruiters to track candidates | `apps/dashboard.py` |
| Bonus: a browser voice agent running the same flow | "Talk to Sofía" in `apps/chat_app.py`; [Architecture, live voice](docs/ARCHITECTURE.md#live-voice-bonus) |
| The brief itself | [docs/TASK.md](docs/TASK.md) |

## Documentation

| Document | What it answers |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it is built: layers, repository map, one message step by step, booking, voice, data, tests. |
| [docs/PHASE1_PROCESS_DESIGN.md](docs/PHASE1_PROCESS_DESIGN.md) | The process the agent follows: personality, stages, fields and rules, outcomes, edge cases. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Every design and technology decision (D-numbers cited in the code), and the open items. |
| [docs/RUNNING.md](docs/RUNNING.md) | Install, configuration, demo data, every command, tests, the model and its limits. |
| [docs/HANDOVER.md](docs/HANDOVER.md) | What Grupo Sazón must decide or provide, and what its lawyers must approve. |

## Compliance, in short

Hiring is high-risk under the EU AI Act (Annex III) and Mexico has its own data law. The agent tells the candidate it is an AI and asks consent first, keeps a human decision-maker, logs every decision with its actor, collects only the screening fields, infers nothing about emotions or personality, treats candidate text as untrusted, and erases a candidate's data on request. This is an engineering baseline, not legal advice; the open items are in [docs/HANDOVER.md](docs/HANDOVER.md).

`CLAUDE.md` and `.claude/` hold the working agreement and skills used to build this with Claude Code (test-first, architecture reviews).
