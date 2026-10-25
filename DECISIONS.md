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
- **Cons of chosen:** risk of long loops and drop-off. Today the only exit from a loop is the 24-hour stall, because there is no withdraw path yet and unclear answers reset the off-topic counter. Revisit if pilot data shows loops.
- **Decided by:** user, 2026-10-25.
