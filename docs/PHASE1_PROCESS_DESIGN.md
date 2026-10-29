# Phase 1: Process design — driver screening agent (Grupo Sazón)

Matches the built agent. The reasons for each choice are in [DECISIONS.md](DECISIONS.md) (D-numbers). *Default* = to confirm with the client.

## 1. Purpose

Screen delivery-driver applicants by chat so recruiters only speak to qualified candidates. Today 60% of candidates don't answer calls and 80% of recruiter time goes to unqualified applicants. The agent screens and summarises; **a recruiter makes every hiring decision**.

## 2. Agent personality

Sofía, an AI assistant for Grupo Sazón recruiting (D72), who says she is an AI in her first message. Warm, direct and respectful, like a friendly recruiter; the informal "tú" in Spanish; patient, never pushy or judgmental. She acknowledges what was said in a few words, uses at most one emoji, and never promises a job, pay or a call time and never decides.

## 3. Conversation stages

| Stage | What happens | Exit |
| --- | --- | --- |
| **0. Consent** | A fixed bilingual disclosure (an AI, an external AI service, reviewed by a recruiter) asks consent to store answers. Read in plain code; nothing reaches the model before a yes (D44). | No or "stop" → close. Unclear → ask again. Yes → next. |
| **0b. Optional CV** | Offered once: upload a PDF to go faster, or just type. Clear answers are read back to be corrected (D71). | Taken or skipped → next. |
| **1–5. Name, experience, availability, schedule, start date** | One question at a time; anything given early is not asked again (D5); a changed answer is confirmed first (D54). Full time is the whole day, so the schedule is not asked (D81). | Valid → next. Unclear → follow-up. |
| **6–7. City, driver's license** | Eligibility, checked as soon as answered. | OK → next. Outside the area or no license → one confirmation question, so a misread never rejects anyone (D40), then a polite close. |
| **8. Decision** | Section 5. | |

## 4. Data fields and validation

| Field | Accepted | Rule |
| --- | --- | --- |
| Full name | Text | Two or more words of letters, hyphens, apostrophes. |
| Driver's license | Yes / no | No → disqualified after confirmation. "No car" is not "no license". |
| City / zone | Text | Fuzzy match to the service areas and nearby towns (sample list, D13). Unsure → "¿Te refieres a Guadalajara?". Not listed → out of area. |
| Availability | Full-time, part-time, weekends | One or more. "2 days a week" is part-time. |
| Preferred schedule | Morning, afternoon, evening, flexible | One. |
| Experience | Years (0–60) and platform (Glovo, Uber Eats, Just Eat, Rappi, DiDi Food, other) | Never disqualifies (D19). Zero only if the candidate says they have none. |
| Start date | "ya", a date, "en 2 semanas" | Converted to a date in code; past is invalid; over 12 weeks away is flagged (*default*). |

Only validated values are stored (JSON); the conversation is the audit record; code builds the recruiter's summary card (D46).

## 5. Outcomes: qualified and disqualified paths

| Outcome | When | The candidate hears | The recruiter gets |
| --- | --- | --- | --- |
| **Qualified** | All fields, license yes, city in area. | They book a 15-minute call themselves: a calendar button in the browser chat, or the next three times as a list. None free or none chosen: "write to us when you want to book" (D81-D83). | Card and booking. |
| **Disqualified** | No license, or outside the area. | "I can't continue with the automated process; a recruiter can review your case" (D52). | Reason and card, in the review queue until a recruiter sets a status. |

## 6. Edge cases

| Situation | Behaviour |
| --- | --- |
| **Stops responding** | One reminder at 24 hours, then `STALLED` 24 hours later; the chat resumes if they write again. |
| **Vague or invalid answer** | Say what is expected, with an example, and ask again. After 5 follow-ups: "I can't continue until you tell me X" and the candidate is `BLOCKED` (D41). A model failure never counts (D39). |
| **Switches language (ES ↔ EN)** | The chat follows the words written, decided in code: a name, a place or a number never changes the language; a sentence in the other language does (D67). |
| **Asks for a person or pay; off-topic; "ignore your rules"** | Person or pay: a fixed sentence (a recruiter will answer), then the next question. Off-topic: a short redirect; the third ends the chat (D55). Candidate text is data, never instructions. |
| **Asks to stop** | A polite close; "continuar" resumes it (D29). |

## 7. Message tone and length

Messaging, not email: 1–2 short sentences and one question per message (D18); no legal text. The model words questions and confirmations (D69); code checks every message (length, one question, language, no pay or time) and sends a fixed text if a check fails or the model is down. The disclosure, closings, call offers and reminders are fixed word for word.

## 8. Compliance, volume and open items

- High-risk under the EU AI Act (Annex III); Mexico has its own data law. Built in: AI disclosure and consent first, a recruiter can overrule any status, every decision logged with its actor, erasure on request, a login per recruiter, no emotion or personality inference. Not legal advice.
- **Volume:** about 1000 applications a week is roughly 0.3 messages a second at the busiest (a fifth in 2 hours, 10 messages each). A load test with a slow, failing fake model passed at about 25 times that (D75).
- **Voice (bonus):** the same flow can be spoken (D93). The AI disclosure and consent are said first; a call time is chosen by saying a day and then a time; no CV by voice. The engine's fixed texts are what is spoken, and no audio is kept.
- **Open for the client:** real service areas; legal review of the texts and of data retention; approved answers about pay; the 12-week rule; single sign-on; a paid model tier.
