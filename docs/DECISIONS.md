# DECISIONS

The settled design and technology choices for the Grupo Sazón screening agent, D1 to D69. Each entry states what is true **now**; a chain of revisions is merged into one entry and lists the numbers it replaces. Before acting against an entry, say so and confirm with the user. Add a short entry when a decision is made.

The full log, with every option considered and its pros and cons, is in git: `git show 4706568~1:DECISIONS.md` (it needs the merge commits of the pull requests; a squash merge would lose it).
All entries were decided by the user (2026-10-25 to 2026-10-27) unless marked *agent* (a fix or detail inside a decision the user had made).

## 1. How the conversation works

- **D5, D6, D27: flow.** The candidate may answer several things in one message; the agent asks only what is missing, in a friendly order (name, experience, availability, schedule, start date, city, license). A disqualifier that is already known (no license, outside the area) ends the chat at once instead of at the end, which protects recruiter time.
- **D40: confirm before rejecting.** A "no license" or out-of-area answer first gets one confirmation question; only a confirming reply ends the chat. Reason: the real model read "no tengo coche" as "no license", and one misread must never reject anyone.
- **D16, D17, D28, D41: unclear answers.** Every field is asked again with an explanation of what is needed. After 5 follow-ups the agent says it cannot continue until the candidate provides it, and repeats that: outcome `BLOCKED` (reason `BLOCKED_ON_<FIELD>`), cleared when the field is given. Model failures never count (D39). *(Replaces the cap of 3, the uncapped license and city, and NEEDS_REVIEW.)*
- **D19, D68: experience.** Years and platform are recorded and never disqualify. Zero years needs the candidate to say they have none (a separate `no_experience` flag); a plain "yes" is not a number. Common spellings of the known platforms are recognised; unknown ones are stored as "other" on purpose (no free text).
- **D26: field rules.** Name: two or more words of letters, hyphens, apostrophes. Start date: more than 12 weeks away is flagged, never rejected. Availability: "N days a week" below a full job is part-time; weekends needs weekends, Saturday or Sunday (D67).
- **D54: a changed answer** is confirmed ("Antes me dijiste X. ¿Lo cambio a Y?") and changed only on a yes, read in plain code.
- **D55: off-topic.** A fixed redirect and the same question; the third off-topic message in total (not in a row; hesitation like "mmm" does not count) ends the chat with a farewell about the messages, never about the person. Final until a recruiter acts.
- **D14, D50: asking for a person or about pay.** Not a strike. A fixed sentence says a recruiter reviews and will answer, then the next question; an event is logged. The agent does not hand over to a person itself.
- **D29, D56: stopping and coming back.** Stop wording ("stop", "para", "me retiro") is read in plain code and closes the chat as `WITHDRAWN`. While applications are open a candidate can come back: after silence or being blocked, after withdrawing ("continuar"), or after declining consent (a later "sí"). It stays closed after qualifying, after a rejection by the agent and after the off-topic exit. A dashboard switch closes applications for everyone.
- **D9, D52: disqualified path.** A polite close with a reason code ("I can't continue with the automated process; a recruiter can review your case"). Every such candidate is in the dashboard's review queue until a recruiter sets a status, so a human can overrule.
- **D7, D8, D36, D48: qualified path and call slots.** Recruiters add call times per country on the dashboard. A qualified candidate is offered the next three free times of their own country as a numbered list (clock time of that country, at least a few hours away). The pick is read in plain code; a booking is atomic, one per candidate, and a recruiter's cancellation queues a message. No free time, or "none", gives the 48-hour message.
- **D10, D35, D38, D58: silence.** One reminder after 24 hours; after 24 more, `STALLED`; any reply resets it. A reminder job (`python -m sazon.reminders`) queues the messages in an outbox for a real channel; it also covers qualified candidates who ignore the offer.
- **D11, D67: language.** The chat mirrors the candidate's language. It is decided in code from the words written (`screener/language.py`): a name, a place or a number changes nothing; the model's own guess is only used when no known word can check a long message.
- **D13: service areas.** A sample list (Madrid, Barcelona, Valencia, Ciudad de México, Guadalajara, Monterrey, with nearby towns) in one place; the client's real list is still needed.

## 2. What the agent says

- **D22, D45: the engine.** A pure-Python state machine (`Screening`) owns the fields, the decision and every message rule; the model only extracts fields and words messages. Reason: rules are unit-testable offline and candidate text can never change a decision.
- **D31, D39: extraction.** One JSON call per message, validated by a Pydantic model whose shape and prompt come from the client's spec. Candidate text is passed as delimited data. Unparseable output is retried once; a failure shows a fixed apology, is logged without candidate data and never costs the candidate a follow-up.
- **D15, D18, D30, D34, D37, D69: wording.** The client writes a persona (tone, length, form of address; Spanish uses "tú"). The model words the questions, follow-ups, place confirmations, change questions, rejection confirmations and the "cannot continue" message, one to two short sentences, given the recent conversation (only after consent, never on the turn that answers the consent question) as data. Every model message is checked (length, one question, language, no pay, job or time, and it must keep the facts it was given); a failed check or an unreachable model sends the fixed text. **Fixed word for word:** the AI disclosure and consent, every closing, the call offers and bookings, the reminders, the error line and all notices (a person, pay, change made, answer kept, off-topic). The model is told a notice was already said.
- **D44: consent is read in plain code.** A conservative Spanish and English word list reads the answer: short clear agreement is yes, a short explicit refusal closes the chat, anything else asks again. Nothing the candidate writes reaches the model before a yes.
- **D46, D66: the recruiter card.** Built by code from the validated data, never repeating the candidate's words or saying anything about the person. It is saved in Spanish with every turn (the audit snapshot) and rebuilt for the screen in the language the recruiter picked.

## 3. Privacy, consent and oversight

- **D12, D34, D51: disclosure and consent.** The first message is fixed, Spanish line then English line: it says the candidate is talking to an AI, that answers are processed by an external AI service and always reviewed by a recruiter, and asks consent to store them. Nothing is asked before a yes. The consent event stores a hash of the exact wording shown. Still a draft until the client's lawyers approve it.
- **D42: recruiter data is separate.** The agent owns outcome, reasons, flags, validated data, card and transcript. Recruiters own a status (`new`, `contacted`, `interview_scheduled`, `hired`, `rejected`, `unreachable`), an assignee and append-only notes, and may set any status on any candidate, so a human can overrule the agent. Every action is an audit event with its actor.
- **D53, D60: erasure and retention.** Every conversation and its data are saved and kept. The dashboard's erase action (with confirmation) overwrites a candidate's data, truncates the database's write-ahead log and leaves an anonymous line; it is for a candidate's request. There is no automatic deletion. How long to keep the rest is a question for the client's lawyers.
- **D57, D65: recruiter accounts.** One account per recruiter, scrypt-hashed in a git-ignored file (`python -m sazon.accounts add NAME`); five wrong passwords lock a name for ten minutes, kept in a file so a restart does not clear it. A prototype: a real deployment needs the company's single sign-on.
- **D43: errors.** An unexpected error never ends the chat or shows technical text; the error with its stack trace (never the candidate's messages) goes to `data/sazon.log` with an id.
- **D33: free-tier data.** Free Gemini prompts may be used by Google to improve its products: use fictional candidates only until a paid or EU-compliant tier is chosen.

## 4. Technology

- **D1, D66: channel.** Terminal chat first (`python -m sazon.chat`); a browser chat to try the agent (`apps/chat_app.py`) saves to a separate demo database and is local only. A real channel (WhatsApp or similar) comes later.
- **D2, D23, D33: model.** Gemini free tier through the OpenAI SDK against Gemini's compatible endpoint, a thin client behind an interface so tests use a fake. Model name from `LLM_MODEL` in `.env`.
- **D3: storage.** SQLite (versioned saves under a write lock, a change counter for the dashboard cache).
- **D4, D47, D66: recruiter tool.** A local Streamlit dashboard (`apps/dashboard.py`): candidate table beside a detail panel with row selection, colored status badges, metric cards, a funnel chart, a call-times page, the applications switch and the review queue. Every word is in a Spanish/English text pack with a language switch.
- **D20, D58: bonuses.** Funnel analytics and the reminder job are built. The voice agent (ElevenLabs) and CV upload are not; CV upload is not recommended (new personal data, more AI Act duties).
- **D21, D24, D25: process.** The Phase 1 design is Markdown in the repo; work is built in slices (domain core, extraction and chat, summary and dashboard) on branches from `main`.

## 5. Code structure

- **D62, D63, D64: engine and client.** `screener/` is the reusable engine and never imports or names a client; `sazon/` is Grupo Sazón. A client is a `ScreeningSpec` (fields, rules, wording, recruiter labels, persona), a `Pack` (fixed texts), a `Client` (service areas, optional call calendar, reminder clock) and its entry points. An incomplete spec or client fails when built. `tests/support/toy_spec.py` is a second client run through the real engine; `tests/engine/test_engine_boundary.py` fails if the engine leaks. Saved states, prompts, fixed texts and the consent hash are pinned by a golden test.
- **D63 differs from its review card:** screening state is a declared list of saved fields and a pure change-proposal function (not a state object with collaborators); the precedence of "what to say first" is a pure function, while the order of checks inside `apply` still lives in `Screening`. A `Store` interface was declined (one adapter).
- **D65: leftovers closed.** Funnel and key numbers counted in SQL; every stored time is naive local time; the login lockout is kept in a file.
- **D66: dashboard and chat app.** Text packs with a completeness check, per-language recruiter texts in the spec, the card rebuilt on screen, the redesign, and the browser chat with a live inspector.
- **D70: second architecture review (2026-10-27), all seven candidates built.** (1) `screener/conversation.py` is the one save cycle: it loads a candidate, lets the caller change it, saves, and applies the caller's policy on a lost race (raise, retry once, skip); the decision event is decided inside the store's transaction. (2) `screener/language.py` holds accent folding, the pick-with-the-client's-default rule, language detection and the pay, hire and time words; the word lists for yes, no, stop and call picks stay in `consent.py` and `slot_choice.py` (a third language still edits those). (3) `screener/recruiter_rules.py` defines NEEDS_REVIEW, TO_CONTACT, BLOCKED, STALLED and AGENT_CLOSED once, as Python and as SQL, with a test that they agree; `RecruiterView(client, pack, language)` gives every screen its labels, cards and rows. (4) `screener/directive.py` holds Directive and Kind, so deciding no longer depends on how a message is worded (it still takes the consent hash and the call-time labels from `phrasing`); notices are a tuple of checked names. (5) The engine says "area", not "city"; the names saved or sent to the model (`pending_city`, `out_of_area`, `confirms_city`) stay as wire names. (6) A table test of the order in which one message is processed (it found and fixed: a place refused and replaced in one message was still followed up). (7) `screener/dialog.py` shares starting a candidate and delivering queued messages. **Declined:** splitting `Screening`'s apply steps into another module (it would move the coupling, not remove it) and splitting reports out of `Store` (one adapter, one file).
- **D69: free wording** is described in section 2; it replaced the tests that said candidate text never reaches the wording prompt (it does now, only as data after consent, and a model that obeys an injection is not believed).

## 6. Reviews and what they fixed

- **D49, D50, D61:** three review rounds, each fix with a test written first. Notable: opt-out never depends on the model; greetings and hesitation are not answers or strikes; injection hardening (data tags removed, 2000-character cap, model text rejected if it mentions pay, a hire or a time); versioned saves and race handling; erasure that really overwrites; accounts safety and login throttle; ids never reused; one database for chat and dashboard.
- **D59:** erasure, return rules, versioned saves, accounts, the applications switch, review queue, funnel and reminder job were built and checked on the real model.
- **D67, D68:** found by trying the chat app: the language flip on a bare place name, "days a week" read as weekends, a plain "yes" saved as zero years, "uber" saved as "other", and screen text in the wrong language. Real-model tests (`pytest -m live`) pin them.

## 7. Open items

**For the client or its lawyers**
- The real service areas (D13).
- Legal review of the consent and farewell wording, and of promises nothing enforces: "a recruiter always reviews", "we reply within 48 hours" ("48 horas" is three literals in the pack).
- How long data may be kept (D60); approved answers about pay.
- Single sign-on instead of the prototype login; a paid model tier with a data-processing agreement (the free tier cannot serve about 1000 applications a week).

**Product**
- A candidate the agent rejected cannot reopen the chat themselves, and the dashboard has no "reopen" action.
- The reminder job must be started by someone and its messages wait for a real channel.
- The voice agent, CV upload and the presentation (the format is not decided).
- The chat app has no login and must not be exposed on a network.

**Technical**
- The candidate table still loads every candidate to filter and search it.
- A third language needs engine edits (word lists, day and month names, the language line of the extraction prompt) and the extraction prompt's filler examples are Spanish.
- The error log is not covered by any retention rule.
- The wording of model-written messages is less predictable: a legal review should read sample conversations, not only the fixed texts.
