# Task checklist

Everything [TASK.md](TASK.md) asks for, whether we do it, and how, in plain words. Status: **Yes**, **Partially**, **No**.

## The client's situation

| What the task says | Done? | How |
| --- | --- | --- |
| About 1000 applications a week | Yes, tested with a fake model | The agent keeps no state in memory, so many chats run at once. An HTTP service answers each message once even if it is sent twice, limits abuse, and asks callers to retry when busy. A load test (200 candidates, a slow fake model that sometimes fails) passes at about 25 times the real peak (assuming a fifth of the week in 2 hours). There is no real channel yet (WhatsApp or similar), and the real model was not load-tested because of the free tier. |
| 60% of candidates don't answer calls | Yes | The candidate chats when it suits them and books their own call (a button with a calendar, or a numbered list) as soon as they qualify. A reminder goes out after 24 hours. |
| 80% of recruiter time goes to unqualified candidates | Yes | The agent screens first. Recruiters only see a short card for each candidate, and those who don't qualify go to a review queue. |
| 13 recruiters | Yes | Each recruiter signs in with email and password (created by the hiring manager), has their own hours and days off, and gets their share of the calls; more recruiters mean more times candidates can book. |
| Spain and Mexico | Yes | Service areas and call times are set per country, in each country's time zone. |

## What the agent must collect and check

| Field | Done? | How |
| --- | --- | --- |
| Full name | Yes | Two or more words of letters. Anything else is asked again. |
| Driver's license (no = disqualified) | Yes | Yes/no. A "no" is confirmed once, then the chat ends politely. |
| City or zone, inside the service areas | Yes | Compared with a list of cities and nearby towns. A typo gets "Did you mean X?". Outside the list ends the chat after one confirmation. The list is a sample until the client gives the real one. |
| Availability (full-time, part-time, weekends) | Yes | Read from the message and checked against those three. |
| Preferred schedule (morning, afternoon, evening, flexible) | Yes | Read from the message and checked against those four. |
| Prior delivery experience (years and platform) | Yes | Years and platform are saved. They never disqualify anyone. |
| Start date | Yes | Read as a date. More than 12 weeks away is flagged for the recruiter, not rejected. |

## Phase 1: process design document

| What the task asks | Done? | How |
| --- | --- | --- |
| A 1 to 2 page document | Yes | [PHASE1_PROCESS_DESIGN.md](PHASE1_PROCESS_DESIGN.md) is about 950 words and prints on 2 pages (A4, 10 pt). The reasons behind each choice are in DECISIONS.md. |
| Conversation stages (order, branching) | Yes | Section 3: consent, seven questions, then a qualified or disqualified path. |
| Agent personality | Yes | Section 2: the agent is Sofía, friendly, short, uses "tú" in Spanish, and says it is an AI. |
| Data fields and validation rules | Yes | Section 4: a table of each field and its rule. |
| Edge case: candidate stops responding | Yes | One reminder at 24 hours. After 24 hours more the chat is marked stalled, and it resumes if they write again. |
| Edge case: invalid or ambiguous answers | Yes | The agent says what it needs and asks again. After 5 tries it says it cannot continue until the candidate answers. |
| Edge case: language switch (Spanish and English) | Yes | The agent answers in the language of the last message. Plain code decides, not the model. |
| Qualified and disqualified paths | Yes | Qualified: offered three call times and booked. Disqualified: a polite close with a reason, and a recruiter can still review. |
| Message tone and length | Yes | Chat messages of 1 to 2 short sentences with one question each. |

## Phase 2: the build

| Requirement | Done? | How |
| --- | --- | --- |
| Python | Yes | Everything is Python. |
| LLM of your choice, justified | Yes | Gemini through its OpenAI-style API. It is free, and good enough for extraction in two languages. The README explains why, and the model sits behind a small interface so it can be swapped. |
| Natural dialogue following the Phase 1 design | Yes | The model words the questions. Plain code decides the order and the rules, and checks every model message. |
| Structured JSON with all fields | Yes | One JSON call per message, checked against a typed schema. |
| Reject invalid input gracefully and ask again | Yes | Each field has a plain-code check and a friendly re-ask. |
| Keep the full conversation history | Yes | Every message is saved, and the recent ones are given to the model. |
| Save conversations and data as JSON or in a database | Yes | SQLite stores the messages, the extracted data and every event. |
| Post-conversation summary with key data | Yes | The recruiter card is built by code from the checked data. |
| Graceful failures, no crashes | Yes | A model failure sends a fixed apology and is logged. An error never ends the chat. Prompt-injection attempts are treated as data. |
| Tool for recruiters to track candidates | Yes | A Streamlit dashboard shows the candidate table with one Estado (contacted, qualified, interview scheduled, hired, rejected), who holds the call, notes, a funnel chart, call times and a review queue. |
| A product recruiters can start using | Partially | Both apps are joined, share one look, refresh themselves and were measured at 5,000 candidates. It runs locally with a prototype login. Still missing, and needs the client: single sign-on, a real channel, a paid model tier, and the real service areas ([HANDOVER.md](HANDOVER.md)). |

## Bonus

| Requirement | Done? | How |
| --- | --- | --- |
| Browser voice agent (e.g. ElevenLabs) | Partially | Built with ElevenLabs: a "Talk to Sofía" button in the chat starts a live call; ElevenLabs listens and speaks and our engine is the brain, so Sofía says the same fixed texts. Tested with fakes. Not yet tried live: it needs your ElevenLabs key (`python -m sazon.voice_launch`). |
| Same flow by voice | Partially | The same screening, rules and consent, spoken. A call time is chosen by saying a day and then a time (no list or button); a day or time that is taken gets the closest one offered. No CV by voice. |
| Other bonus features | Yes | Optional CV upload (PDF), funnel analytics, a 24-hour reminder job, a funnel from application to hire with each candidate's path, a call calendar where recruiters book calls for candidates, a browser chat to try the agent, and an HTTP service with a load test. |

## Deliverables

| Deliverable | Done? | How |
| --- | --- | --- |
| Phase 1 process design document | Yes | Written, 2 pages, and kept in line with the code. |
| Phase 2 code: agent and recruiter tool | Yes | `screener/` is the engine, `sazon/` is Grupo Sazón, and `apps/` holds the dashboard and the browser chat. About 1000 tests (D85). |
| Presentation of the work | No | The format has not been chosen yet. |

## Required by law (not in the task, but a hiring tool needs it)

| Rule | Done? | How |
| --- | --- | --- |
| Tell candidates they talk to an AI, and ask consent | Yes | The first message is fixed text. Nothing is asked before a yes. |
| A person makes the final decision | Yes | The agent only screens and moves a candidate through contacted, qualified and interview scheduled. A recruiter or the hiring manager decides hired or rejected and can overrule any state. |
| Log decisions and their data | Yes | Every decision is an event with its actor. |
| Collect only what is needed, and allow erasure | Yes | Only the screening fields are collected. Erasure overwrites the data. |
| No emotion or personality inference | Yes | Nothing like that is asked or stored. |
| Legal review of the texts | No | Needs the client's lawyers. |
