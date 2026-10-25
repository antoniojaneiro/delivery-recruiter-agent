# DECISIONS

Log of design and tech decisions for the Grupo Sazón screening agent. Each entry records the choice, the options that were considered, and the trade-offs. Decisions can be changed. Before acting against an entry, say so and confirm with the user.

## D1: Channel (where candidates talk to the agent)

- **Chosen:** Terminal chat first. Move to a real channel later.
- **Options considered:**
  - WhatsApp Business API: highest candidate reply rate in Spain and Mexico. Needs a provider account, Meta approval and per-message cost.
  - Browser web chat: simple to demo. Candidates must open a link, so replies are likely lower.
  - SMS: works on any phone. Costly per message and has weaker reply rates.
  - Terminal chat: free, zero setup, fastest to build. Does not look like a product to candidates.
- **Pros of chosen:** free, no accounts, fastest path to a working agent. Keeps the channel decision separate from the core logic.
- **Cons of chosen:** candidates cannot use it, so it is a prototype. The channel adapter must be built later.
- **Decided by:** user, 2026-10-25.

## D2: LLM provider

- **Chosen:** Gemini free tier, via the course wrapper `course_llm.py`.
- **Options considered:**
  - Ollama (fully local): no account and no data leaves the machine. Needs a 2-5 GB download and a slower, weaker model at Spanish extraction.
  - Groq free tier: very fast. Tighter free limits.
  - Paid OpenAI: most reliable structured output. Costs money.
- **Pros of chosen:** strong quality, free key (Google AI Studio sign-in, no card), already wired in the course. Works with the OpenAI-style SDK.
- **Cons of chosen:** candidate data goes to Google's servers, which matters for GDPR. Free-tier rate limits. The key must stay in `.env`.
- **Decided by:** user, 2026-10-25.

## D3: Storage

- **Chosen:** SQLite (single file, built into Python).
- **Options considered:**
  - One JSON file per candidate: readable, but the dashboard reads every file to filter.
  - One big JSON file: rewrites everything on each save, breaks on crashes.
  - Postgres or cloud DB: production grade, but needs a server or account.
- **Pros of chosen:** real queries and filters for the dashboard, no install, safe writes.
- **Cons of chosen:** slightly more code than JSON. Single writer, which is fine for this scope.
- **Decided by:** user, 2026-10-25.

## D4: Recruiter tool

- **Chosen:** Streamlit dashboard, run locally.
- **Options considered:**
  - Terminal commands: no extra dependency, but hard for non-technical recruiters.
  - Both CLI and dashboard: twice the work for the same data.
  - Defer the tool: the brief requires it.
- **Pros of chosen:** looks like a product, filters and status changes, easy to demo, easy to move online later.
- **Cons of chosen:** one extra dependency. Local only, not shared between recruiters.
- **Decided by:** user, 2026-10-25.

## D5: Flow shape (how fields are collected)

- **Chosen:** Hybrid. The candidate can answer several things in one message. The agent asks only for fields still missing.
- **Options considered:**
  - Fixed, one question at a time: predictable and easy to test, but robotic and repetitive.
  - Free chat, then extract: most natural, but misses fields and is hardest to validate.
- **Pros of chosen:** natural and shorter than fixed, still structured enough to validate.
- **Cons of chosen:** needs logic that tracks which fields are filled.
- **Decided by:** user, 2026-10-25.

## D6: Question order and disqualifier timing

- **Chosen:** Friendly order (name and experience first). All fields are checked at the end, then the decision is made.
- **Options considered:**
  - Disqualifiers first (license, city): ends non-qualifiers quickly, saves recruiter and candidate time, but can feel like an interrogation.
  - Ask everything, decide later: same as the chosen option in effect, but the opening order differs.
- **Pros of chosen:** warmer start, better candidate experience.
- **Cons of chosen:** candidates who will be disqualified spend longer in the chat. This works against the client's problem of recruiter time spent on unqualified candidates. Revisit if pilot data shows long chats for rejected candidates.
- **Decided by:** user, 2026-10-25.
- **Open tension:** this conflicts with the client problem. Flag if it comes up again.

## D7: Qualified path

- **Chosen:** Offer a call time now.
- **Options considered:**
  - Mark ready and send a recruiter summary: clear next step, but the recruiter still has to schedule.
  - Store as qualified only: simplest, but the candidate hears nothing after qualifying, which makes the no-response problem worse.
- **Pros of chosen:** fewest steps for the candidate.
- **Cons of chosen:** needs a source of available times. Calendar integration would add setup, so a recruiter-defined slot list is likely needed. How slots are provided is still open.
- **Decided by:** user, 2026-10-25.

## D8: Source of call slots

- **Chosen:** Recruiter-set slot list, kept in a simple config or dashboard page. The agent offers the next free slots.
- **Options considered:**
  - Google Calendar integration: real availability, but needs OAuth and a Google account per recruiter.
  - Candidate proposes a time, recruiter confirms: no slot management, but no firm time is offered.
- **Pros of chosen:** no accounts or integrations, fits the no-setup goal.
- **Cons of chosen:** lists go stale unless recruiters maintain them. No real calendar check.
- **Decided by:** user, 2026-10-25.

## D9: Disqualified path

- **Chosen:** Polite close with a reason code (for example no license, outside service area). Stored for the recruiter.
- **Options considered:**
  - Polite close + keep for future roles: builds a talent pool, but needs explicit GDPR consent, retention rules and deletion on request.
  - Polite close + explain how to qualify: helpful sometimes, but rarely actionable and can promise things the client did not approve.
- **Pros of chosen:** respectful, simple, gives the recruiter clean reporting.
- **Cons of chosen:** candidates who might qualify later must reapply.
- **Decided by:** user, 2026-10-25.

## D10: No reply mid-conversation

- **Chosen:** One reminder after 24 hours. If still no reply, mark the candidate as stalled, visible in the dashboard.
- **Options considered:**
  - Two reminders over 3 days: more recovery, but can feel like spam and conflicts with the message-tone guidelines.
  - No reminders: simplest, but loses candidates with no second chance.
- **Pros of chosen:** one nudge catches most people, and stalled candidates stay visible for recruiters.
- **Cons of chosen:** in terminal mode the 24-hour wait must be simulated, for example with a command.
- **Decided by:** user, 2026-10-25.

## D11: Language

- **Chosen:** Mirror the candidate's language on each message (Spanish or English).
- **Options considered:**
  - Lock to one language chosen at start: simpler, but a mid-chat switch may not be understood.
  - Always Spanish, English on request: matches the main market, still needs a switch path.
- **Pros of chosen:** natural, no confusion about which language is in use.
- **Cons of chosen:** language detection per message. Screening questions need templates in both languages.
- **Decided by:** user, 2026-10-25.

## D12: AI disclosure and consent

- **Chosen:** The first message says the candidate is talking to an AI and asks consent to store their answers. No screening questions until consent is given.
- **Options considered:**
  - Disclose at start with no consent gate: no lawful basis recorded for storing personal data.
  - Disclose at the end: breaks the transparency expectation, since candidates answer personal questions unaware.
- **Pros of chosen:** matches EU AI Act transparency and GDPR consent expectations. Gives a clear record.
- **Cons of chosen:** one extra message. A candidate who declines cannot be screened.
- **Decided by:** user, 2026-10-25.
- **Note:** this is an engineering interpretation. Confirm with the client's legal team before any real use.

## D13: Service areas

- **Chosen:** Sample list for now (Madrid, Barcelona, Valencia, Ciudad de México, Guadalajara, Monterrey), kept in one config file to swap for the real list later.
- **Options considered:**
  - Wait for the real list: correct, but blocks building.
  - Accept any city: simplest, but the brief requires the outside-area disqualifier, which would not work.
- **Pros of chosen:** unblocks building, a single place to change.
- **Cons of chosen:** test results only reflect the sample areas.
- **Decided by:** user, 2026-10-25.
- **Open:** the real list from the client is still needed before any pilot.

## D14: Candidate asks for a human

- **Chosen:** Politely decline and keep screening.
- **Options considered:**
  - Flag for recruiter and tell the candidate when they'll hear back: honours the request, sets expectations, needs a flag in the dashboard.
  - Stop the chat with no action: simplest, but the candidate is effectively lost.
- **Pros of chosen:** simple flow, nothing extra to build.
- **Cons of chosen:** candidates who want a human are frustrated and may drop out. It also weakens the human-oversight principle in CLAUDE.md, since a candidate cannot reach a person through the agent. A flag would still be cheap to add later.
- **Decided by:** user, 2026-10-25.
- **Flag:** revisit if pilot data shows drop-off at this point.

## D15: Tone and formality

- **Chosen:** Friendly "tú" in Spanish.
- **Options considered:**
  - Formal "usted": professional but stiff for chat.
  - Neutral wording with no pronoun: avoids the choice but reads awkwardly.
- **Pros of chosen:** warm, matches gig and delivery job messaging.
- **Cons of chosen:** a few candidates may find it too casual.
- **Decided by:** user, 2026-10-25.

## D16: Ambiguous answers

- **Chosen:** Keep asking until the answer is clear.
- **Options considered:**
  - Ask once more, then flag for recruiter: a clear answer most of the time, and unclear cases go to a human. Recommended.
  - Accept raw text as-is: structured fields become unreliable, which the brief forbids.
- **Pros of chosen:** every field ends up clean.
- **Cons of chosen:** repeated questions can frustrate candidates and cause drop-off, the same problem the client has now. Needs a cap, see the open question below.
- **Decided by:** user, 2026-10-25.
- **Open:** whether to add a maximum number of follow-ups per field.

## D17: Follow-up cap per field

- **Chosen:** Maximum of 3 follow-up questions per field. After that, the field is flagged for recruiter review.
- **Options considered:**
  - Cap of 2: fewer frustrated candidates, more fields left for humans.
  - No cap: no unclear fields, but loops can drop candidates.
- **Pros of chosen:** keeps "ask until clear" while preventing endless loops.
- **Cons of chosen:** some candidates will still be asked three times, which can frustrate them.
- **Decided by:** user, 2026-10-25.

## D18: Message length and style

- **Chosen:** 1-2 short sentences per message, one question each.
- **Options considered:**
  - Short paragraph with 2-3 questions: fewer messages, but candidates skip some questions and need follow-ups.
  - Longer explanations: unlike chat, more drop-off.
- **Pros of chosen:** reads like a phone chat, better answer quality.
- **Cons of chosen:** more messages per conversation.
- **Decided by:** user, 2026-10-25.

## D19: Experience is not a disqualifier

- **Chosen:** Record years and platform. Never disqualify on experience.
- **Options considered:**
  - Disqualify if no experience: a stronger filter than the brief specifies.
  - Flag as lower priority: needs a ranking rule the brief does not define.
- **Pros of chosen:** matches the brief (experience is a field, not a rule), keeps the funnel wide.
- **Cons of chosen:** recruiters may see more candidates with no experience.
- **Decided by:** user, 2026-10-25.

## D20: Bonus features

- **Chosen:** Build all bonus features, but only after the basic version (Phase 2 core plus the Phase 1 doc) is finished.
- **Bonus set:** funnel analytics, automatic 24-hour reminder, voice agent (ElevenLabs), candidate CV upload.
- **Options considered:** choose a subset (for example analytics and voice only), which keeps scope smaller.
- **Pros of chosen:** full bonus coverage; sequencing keeps the core first.
- **Cons of chosen:** scope is large. CV upload adds file parsing and a new category of personal data, which increases GDPR and EU AI Act obligations. Flag if time runs short.
- **Decided by:** user, 2026-10-25.

## Deferred

- **Voice agent (bonus):** after the core works. Would use the ElevenLabs `agents` skill, which needs an API key.
- **Presentation format** (the brief says "present your work"): not decided. Does not change what gets built.
- **Field details** (name rules, start-date parsing, a driver's license answer of "unsure"): to decide during the build, with proposed defaults written into the Phase 1 doc.

## Proposed defaults (P1 and P2 confirmed in D26)

Written into [PHASE1_PROCESS_DESIGN.md](PHASE1_PROCESS_DESIGN.md) as engineering defaults. Confirm or change each one.

- **P1 Name rule:** at least two words of letters, spaces, hyphens and apostrophes (confirmed, changed in D26).
- **P2 Start date:** more than 12 weeks away is recorded but flagged (confirmed in D26).
- **P3 Off-topic messages:** two in a row end the chat with `ENDED_OFF_TOPIC`.
- **P4 Retention:** disqualified data deleted after 6 months. Qualified and stalled data kept for the active hiring cycle. Needs legal review.
- **P5 Files and photos:** not accepted in Phase 2. The agent asks for text.
- **P6 Pay and schedule questions:** answered only with client-approved information. Otherwise a recruiter answers, and the question is logged.
- **P7 Asks for a human:** logged as an event, still declined (D14).

## D21: Phase 1 doc format

- **Chosen:** Markdown in the repo.
- **Options considered:** PDF (polished, hard to edit and version), Word (familiar for business readers, binary in git).
- **Pros of chosen:** versioned with the code, free, readable on GitHub, can be exported to PDF later.
- **Cons of chosen:** less polished for a non-technical reader.
- **Decided by:** user, 2026-10-25.

## D22: Conversation engine

- **Chosen:** Pure-Python state machine owns fields, follow-up caps and the qualified/disqualified decision. The LLM only extracts fields from the candidate message and phrases the short reply.
- **Options considered:**
  - LangGraph state graph: matches course module 4, but heavy for a linear flow with hybrid skipping.
  - Single LLM with tool calls: least code, but hard to test, the model makes the decision, and it is weak against prompt injection.
- **Pros of chosen:** rules are unit-testable offline (D5, D16, D17). Candidate text can never change a decision.
- **Cons of chosen:** more code than a prompt-only agent.
- **Decided by:** user, 2026-10-25.

## D23: LLM client

- **Chosen:** Own thin client (`openai` SDK against Gemini's OpenAI-compatible endpoint), key from this repo's `.env`, behind an interface so tests use a fake. Refines D2: the course wrapper is read for the pattern only, not imported.
- **Options considered:** import `course_llm.py` by absolute path (zero code, but breaks on other machines, couples the repo to private course files, may touch the course `.env`).
- **Pros of chosen:** self-contained, no course content copied, no real keys read.
- **Cons of chosen:** a little extra code.
- **Decided by:** user, 2026-10-25.

## D24: Build order

- **Chosen:** Slice 1 domain core with no LLM (models, validators, follow-up cap, decision, SQLite store). Slice 2 LLM extraction and terminal chat. Slice 3 summary and Streamlit dashboard.
- **Options considered:** thin end-to-end first (earlier demo, but rules tested last and more rework).
- **Decided by:** user, 2026-10-25.

## D25: Branching

- **Chosen:** Merge the Phase 1 docs branch to `main` first, then branch Phase 2 work from `main`. Done 2026-10-25 (fast-forward to `959d195`).
- **Decided by:** user, 2026-10-25.

## D26: Slice 1 rule details

- **Consent reply:** the agent always speaks first with the consent question, so nothing is collected before it. If the consent reply also contains data, it is processed only after a yes. After a no, it is discarded.
- **Unclear answers:** each follow-up must say what exactly is unclear and what a good answer looks like, so the conversation can move forward. The 3-follow-up cap (D17) still applies.
- **Cap hit on license or city:** superseded by D28 (no cap on these two fields).
- **P1 confirmed (changed):** name is 2+ words of letters, spaces, hyphens and apostrophes (accents allowed).
- **P2 confirmed:** start date more than 12 weeks away is recorded and flagged, never rejected.
- **Decided by:** user, 2026-10-25.

## D27: Early disqualification (updates D6)

- **Chosen:** A disqualifier that is already known (no license, out-of-area city) ends the chat with a polite close, even if other fields are still missing. Friendly question order (D6) stays, but the decision is not delayed.
- **Options considered:** finish the flow and decide at the end (D6 as written): full data on everyone, but ineligible candidates answer more questions.
- **Pros of chosen:** saves candidate and recruiter time, which is the client's core problem. Closes the tension noted in D6.
- **Cons of chosen:** less data on rejected candidates.
- **Decided by:** user, 2026-10-25.

## D28: Eligibility fields are not capped (updates D17, replaces the D26 assumption)

- **Chosen:** License and city are asked again, with a specific explanation each time, until the answer is clear. The 3-follow-up cap (D17) applies to the other fields only. There is no NEEDS_REVIEW outcome for eligibility.
- **Options considered:** higher cap then recruiter review; disqualify as unverifiable.
- **Pros of chosen:** eligibility is always known before qualifying or rejecting.
- **Cons of chosen:** risk of long loops and drop-off. The exit from a loop is withdrawal (D29) or the 24-hour stall. Unclear answers reset the off-topic counter, so that rule does not end the loop. Revisit if pilot data shows loops.
- **Decided by:** user, 2026-10-25.

## D29: Candidate can withdraw at any time

- **Chosen:** A withdraw request ("stop", "para", "no quiero continuar") ends the chat with outcome `WITHDRAWN`, logs a `withdrawn` event and asks nothing more. It wins over every other outcome except declined consent. Slice 2 must detect the request, and the candidate's data stays under the retention rules until deleted on request.
- **Options considered:** no withdraw path (only the 24-hour stall ends a loop, and consent withdrawal would be harder than giving it).
- **Pros of chosen:** GDPR-aligned, gives uncapped license and city questions (D28) a real exit.
- **Cons of chosen:** an LLM misreading could end a chat early. Include withdraw wording in the slice 2 extraction evals.
- **Decided by:** user, 2026-10-25.

## D30: Who writes candidate messages

- **Chosen:** Code decides what to ask and why; the LLM phrases 1-2 short sentences in the candidate's language (D11, D15, D18). A length check and a fixed fallback template protect against bad output.
- **Options considered:** fixed templates in both languages (predictable, robotic); hybrid with fixed consent/close texts (safer legal wording, more code).
- **Pros of chosen:** natural, handles language switching.
- **Cons of chosen:** wording varies run to run. The consent and AI-disclosure text should be reviewed by the client's legal team (D12), so it may become fixed later.
- **Decided by:** user, 2026-10-25.

## D31: Extraction

- **Chosen:** One JSON call per candidate message, validated by a Pydantic schema. The call returns every field it can see plus intent flags (consent, withdraw, wants human, off-topic). The candidate text is passed as delimited data, never as instructions. Invalid output becomes a follow-up, not a crash.
- **Options considered:** separate small calls per intent and field (simpler prompts, 3-4x the calls on a rate-limited free tier).
- **Decided by:** user, 2026-10-25.

## D32: Terminal chat

- **Chosen:** Plain loop with commands: `/new`, `/resume <id>`, `/wait24h` (simulates the stall and reminder, D10), `/quit`. All writes go through `session.commit`.
- **Options considered:** also a scripted demo mode without the LLM (safer to present, extra code).
- **Decided by:** user, 2026-10-25.

## D33: Gemini model and data

- **Chosen:** The model name is read from `LLM_MODEL` in `.env` with a default, because Gemini names drift (a 404 gives a clear message). The client uses the OpenAI SDK against Gemini's OpenAI-compatible endpoint with timeouts and bounded retries on 429/5xx.
- **Data rule:** Gemini free-tier prompts may be used by Google to improve its products. Use only fictional candidates until a paid or EU-compliant tier is chosen. Add to D2's cons.
- **Decided by:** user (D2, D23), 2026-10-25. The refinements are mine.

## D34: Consent and AI-disclosure message is a fixed template (deviates from D30)

- **Chosen:** The first message is fixed text, Spanish line then English line, with the AI disclosure and the consent question. It is never LLM-written. Later replies mirror the candidate's language (D11).
- **Options considered:** Spanish only (shorter, but an English-only candidate may not understand the consent question); LLM-written (natural, but the disclosure is not guaranteed).
- **Pros of chosen:** the legal disclosure (D12) is always present and reviewable by the client's legal team.
- **Cons of chosen:** a longer first message.
- **Decided by:** user, 2026-10-25.

## D35: Stall and reminder model (refines D10)

- **Chosen:** The first `/wait24h` sends the single reminder and logs a `reminder_sent` event. The second sets outcome `STALLED`, visible in the dashboard. Any new candidate message resumes the chat.
- **Decided by:** user, 2026-10-25.

## D36: Call slots deferred (refines D7, D8)

- **Chosen:** The slot list and the booking offer are built in slice 3 with the dashboard. Until then, qualified candidates hear the Phase 1 fallback: a recruiter will reply within 48 hours. The LLM never invents times.
- **Decided by:** user, 2026-10-25.

## D37: Fixed texts for closes, reminder and errors (deviates from D30)

- **Chosen:** The closes (qualified, disqualified, withdrawn, off-topic), the reminder and the technical-error message are fixed Spanish and English templates, with the AI-disclosure message (D34). Only questions, follow-ups and city confirmations are LLM-phrased, behind length, URL and one-question checks with template fallbacks.
- **Options considered:** let the LLM phrase them too (more natural, but it could promise a job, pay or a call time).
- **Pros of chosen:** the riskiest texts can be reviewed by the client's legal team and cannot be improvised.
- **Cons of chosen:** less natural wording at the end of the chat.
- **Decided by:** user, 2026-10-25.

## D38: One reminder per period of silence (refines D35)

- **Chosen:** Any candidate reply resets the reminder, so each period of silence gets one reminder before `STALLED`.
- **Options considered:** one reminder per candidate in total (stricter on spam, lets a second silence stall with no nudge).
- **Decided by:** user, 2026-10-25.

## D39: Model failures never cost the candidate a follow-up (refines D31)

- **Chosen:** Unparseable model output is retried once. If it still fails, or the model is unreachable, the candidate gets the fixed technical-problem message, no follow-up is counted, and a `model_failure` event (`unparseable` or `unreachable`, no candidate data) is logged. An empty response from Gemini is treated as unreachable.
- **Options considered:** keep charging a follow-up and log it (loops always end, but our glitches can push answers to REVIEW); apologise at once with no retry (cheaper, more glitches reach the candidate).
- **Cons of chosen:** one extra call on a rate-limited tier. A message that always breaks the model repeats the apology until the 24-hour stall.
- **Decided by:** user, 2026-10-25.

## D40: Confirm before rejecting (refines D27)

- **Chosen:** A "no license" or out-of-area answer first gets one fixed confirmation question ("Just to confirm: is it right that you don't have a driver's license?"). Only a confirming reply, or repeating the same answer, ends the chat. A contradicting answer clears it. The extraction prompt also says a license is not a car or any vehicle.
- **Why:** the real model (gemini-3.5-flash-lite, first live run) read "no tengo coche" ("I don't have a car") as "no license". With D27 alone, one misread would reject a candidate with no human involved. The sharpened prompt fixed that case in a live re-check, but one misread must never be enough.
- **Options considered:** only sharpen the prompt (no extra message, nothing stops the next misread); require a license keyword in the candidate's words (brittle across Spanish and Mexican wording).
- **Pros of chosen:** a single model error can never reject a candidate.
- **Cons of chosen:** one extra message for candidates who really are ineligible, which slightly weakens D27's time saving.
- **Decided by:** user, 2026-10-25.

## D41: Insist five times, then BLOCKED (replaces D16, D17 and D28; removes NEEDS_REVIEW)

- **Chosen:** For every field the screening collects (all are necessary, and experience can always be answered with "0"), an unclear answer gets a follow-up that explains the information is needed to move forward. After 5 follow-ups, the next unclear answer gets a fixed message: "I can't continue with your application until you tell me X". The candidate gets that same reply to every later message until they provide X. The outcome is `BLOCKED` with reason `BLOCKED_ON_<FIELD>`, visible in the dashboard, and it clears when the field is provided. A blocked candidate is still reminded and can stall (D35). Model failures never count (D39).
- **Removed:** the 3-follow-up cap, the `NEEDS_REVIEW` flags, and storing the candidate's raw words in place of a value. `extracted` now only holds validated values, so it has one consistent shape. The earlier "uncapped license and city" rule (D28) is replaced by this single rule.
- **Options considered:** a separate `review` map for raw answers; a wrapper object on every field; keeping the mixed shape.
- **Pros of chosen:** one simple rule for all fields, clean typed JSON, and recruiters see stuck candidates as a clear status.
- **Cons of chosen:** a candidate who cannot or will not answer is stuck until the 24-hour stall. Nothing reaches a recruiter except the `BLOCKED` status, so recruiters must watch that filter. Revisit if pilot data shows many blocked candidates.
- **Decided by:** user, 2026-10-25.

## D42: Recruiter data is separate from the agent's data

- **Chosen:** The agent owns `outcome`, `reasons`, `flags`, `extracted`, the summary and the transcript. Recruiters own a separate record: a hiring status (`new`, `contacted`, `interview_scheduled`, `hired`, `rejected`, `unreachable`, default `new`), an assignee, and append-only notes. Chat turns never touch the recruiter record and recruiter actions never touch the agent's data. A recruiter may set any status on any candidate, including one the agent disqualified, so a human can always overrule the agent. Every recruiter action is an audit event whose `actor` is `recruiter:<name>`; agent events have actor `agent`.
- **Also done:** the decision's reasons and flags are stored with every turn, so the dashboard filters by `BLOCKED_ON_NAME` or `START_DATE_FAR` without rebuilding the screening. The store waits up to 10 seconds on a busy database so the dashboard and chat can write at the same time. Databases created earlier are upgraded in place.
- **Options considered:** let recruiters edit the agent's fields directly (fixes misreads at the source, but needs protection against the next chat turn overwriting the fix and a per-field marker for human edits).
- **Pros of chosen:** overwrite conflicts cannot happen, and the agent's decision and the human's decision stay visibly distinct (human oversight).
- **Cons of chosen:** a recruiter cannot correct an extracted value in place; they add a note.
- **Decided by:** user, 2026-10-25.

## D43: Unexpected errors in the terminal chat

- **Chosen:** Any unexpected error, in a message or in `/new`, `/resume` or `/wait24h`, never ends the program. The candidate side shows the usual short apology, the full error (type and stack trace, never the candidate's messages) is appended to `data/sazon.log`, and the terminal prints an operator line such as `[error 3f2a1c: see data/sazon.log]`. If the opening of the chat fails, the program stays up and asks for `/new`. A database that cannot be opened at startup exits with a clear message. A log that cannot be written never makes things worse.
- **Options considered:** log silently with no error line (cleaner demo, but easy to miss a problem); a `--debug` flag that crashes loudly (fast for developers, one more mode).
- **Pros of chosen:** nothing is hidden, bugs are traceable in a demo or pilot, and candidates never see technical text.
- **Cons of chosen:** a small log file to look after. The log should be covered by the retention rules (P4), since stack traces can in rare cases include fragments of data.
- **Decided by:** user, 2026-10-25.

## D44: The consent reply is read in plain code, never by the model (refines D12, D26, D31)

- **Chosen:** The answer to the consent question is read by `sazon/consent.py`, a conservative Spanish and English word list. No extraction call is made and nothing the candidate writes reaches the model until they have said yes. The reply is read as:
  - **yes** for short, clear agreement ("sí", "vale", "ok", "yes", "no hay problema", "no problem"), or a clear agreement word followed by punctuation and more text without a condition ("sí, soy Juan de Madrid"). The extra text is ignored and asked for normally after the yes.
  - **no** only for short, explicit refusals ("no", "no gracias", "no quiero", "no thanks"), and also "stop", "para" and "no quiero continuar" said before consent. All close the chat as `NO_CONSENT` at once, with no confirmation question, because nothing has been stored.
  - **unclear** for anything else (questions, conditions, unknown words, long messages). The consent question is asked again, with no limit: it costs no model call and the 24-hour stall ends an abandoned chat.
- **Why:** the consent answer used to be sent to Google's model before the candidate had agreed to anything, the weakest point of the privacy design. A misread "no" would also end a chat for good, so a refusal must be short and explicit.
- **Options considered:** keep the model for the consent reply (understands any wording and keeps data given with the yes, but the text leaves our system before consent); ask "just to confirm" before closing on a no (no accidental close, but pressing someone who has just refused can read as pushy under GDPR).
- **Cons of chosen:** an unusual way of saying yes is read as unclear and asked again. Data given with the yes is asked for again.
- **Supersedes:** the part of D26 that used data from the consent reply, and the consent intent in D31.
- **Decided by:** user, 2026-10-25.

## D45: All message rules live in Screening; turn.py only does I/O

- **Chosen:** `Screening` decides everything about a message: consent, blocking, confirmations, what to ask next, the reminder and stall, and the model-failure directive. `turn.py` only loads and saves, calls the model, and writes the reply. `session.py` reaches the screening through `syncing_events()`, so the "events saved" counter is private and rolled back if saving fails. Language, fields and reasons are enums (`Language`, `Field`, `Reason`). An unsupported language keeps the last supported one, starting in Spanish. The two fake LLMs raise `LLMError` when their script runs out, like the real client.
- **Options considered:** only add methods for the private bits and keep the split (smaller, but new rules would keep landing in the wrong file).
- **Pros of chosen:** every rule is testable without a model or a store, and nothing writes the screening's private state from outside.
- **Cons of chosen:** a larger `Screening` class. Revisit if it grows further.
- **Decided by:** user, 2026-10-25.
