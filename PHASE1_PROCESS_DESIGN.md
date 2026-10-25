# Phase 1: Process Design — Driver Screening Agent (Grupo Sazón)

Status: draft for review. Every decision traces to [DECISIONS.md](DECISIONS.md) (D1–D36). Items marked **Proposed default** are engineering choices to confirm with the client.

## 1. Purpose

Screen delivery-driver applicants by chat, so recruiters only speak to qualified candidates. Today, 60% of candidates don't answer calls and 80% of recruiter time goes to unqualified applicants.

Phase 2 starts in the terminal and moves to a real messaging channel later (D1).

## 2. Agent personality

- **Who it is:** an AI assistant for Grupo Sazón recruiting. It says so in the first message.
- **Tone:** warm, direct, friendly "tú" (D15). Patient, never pushy, never judgmental.
- **Language:** replies in the language of the candidate's last message, Spanish or English (D11).
- **Does not:** promise a job, give pay figures beyond what the client approves, or make the final hiring decision. A recruiter does that.

## 3. Conversation stages

| Stage | What happens | Exit |
| --- | --- | --- |
| **0. Consent** | AI disclosure and consent to store answers (D12). | No consent → polite close, reason `NO_CONSENT`. Yes → stage 1. |
| **1. Name** | Full name. | Valid → 2. |
| **2. Experience** | Years and platform(s) (D19: recorded, never disqualifies). | Always → 3. |
| **3. Availability** | Full-time, part-time, weekends (one or more). | Valid → 4. |
| **4. Preferred schedule** | Morning, afternoon, evening, flexible. | Valid → 5. |
| **5. Start date** | When they can start. | Valid → 6. |
| **6. City / zone** | Checked against the service areas as soon as it is answered (D27). | In area → 7. Outside → disqualified, chat ends. |
| **7. Driver's license** | Yes or No, checked as soon as it is answered (D27). | Yes → 8. No → disqualified, chat ends. |
| **8. Decision** | See section 5. | Qualified, disqualified, or stalled. |

Order is friendly (D6): name and experience first, eligibility questions last. A disqualifier that is already known ends the chat politely, even if fields are missing (D27). Hybrid collection (D5): if a message already answers later fields, the agent records them and skips the question.

## 4. Data fields and validation

| Field | Accepted input | Validation | If invalid |
| --- | --- | --- | --- |
| Full name | Any text | At least two words of letters, spaces, hyphens or apostrophes (accents allowed), e.g. García-López, O'Brien. | Ask for first and last name. |
| Driver's license | Sí / No | No → disqualify (`NO_LICENSE`). "Unsure" → ask again. | Ask again with a specific explanation, no cap, until clear (D28). |
| City / zone | Any text | Fuzzy match to the service-area list (D13); if unsure, confirm: "¿Te refieres a Guadalajara?" | Not in list → disqualify (`OUT_OF_AREA`). Unclear → ask again, no cap (D28). |
| Availability | Full-time, part-time, weekends | One or more of the three. | Ask which fits. |
| Preferred schedule | Morning, afternoon, evening, flexible | One of four. | Ask which fits. |
| Experience | Years (number, "ninguna") + platform (Glovo, Uber Eats, other) | Years is a number ≥ 0. Platform is free text, normalised to a known list or "other". | Ask once more (D16, cap 3). Never disqualifies. |
| Start date | "ya", a date, or "en N semanas" | Converted to a date. Past dates are invalid. **Proposed default:** more than 12 weeks away is recorded but flagged. | Ask for a date or a rough timeframe. |

**Follow-up cap (D16, D17):** each field gets at most 3 follow-up questions. After that, the answer is stored as-is with status `NEEDS_REVIEW`, so a recruiter sees it. The conversation continues.

## 5. Outcomes

| Outcome | When | What the candidate hears | What the recruiter gets |
| --- | --- | --- | --- |
| **Qualified** | License yes, city in area, all fields collected. | Thanks, and a recruiter will reply within 48 hours. The slot offer from the recruiter's list (D7, D8) comes with the dashboard (D36); the agent never invents call times. | Summary card with all fields and flags. |
| **Disqualified** | `NO_LICENSE`, `OUT_OF_AREA`, or `NO_CONSENT`. | Polite close: thanks, the reason in one sentence, and that they can apply again later (D9). | Reason code only. |
| **Stalled** | No reply for 24 hours: one reminder is sent, and after 24 more hours without a reply the candidate is marked `STALLED` (D10, D35). A new message resumes the chat. | Reminder: short, one line, offer to continue. | Status `STALLED`, last stage reached. |
| **Withdrawn** | The candidate asks to stop at any time (D29). | Confirmation that the chat is closed, no more questions. | Status `WITHDRAWN`, last stage reached. |
| **Needs review** | A field other than license or city hit the 3-follow-up cap. The rest of the flow continues. | Normal path. | The raw answer, flagged. |

## 6. Edge cases

| Situation | Behaviour |
| --- | --- |
| **Stops responding mid-chat** | One reminder at 24 hours, then `STALLED` (D10). The conversation can resume if they write again. |
| **Vague answer** ("a veces", "varios") | Ask a specific follow-up with examples. Up to 3 times, then `NEEDS_REVIEW` (D16, D17). |
| **Invalid answer** ("no sé" for start date, a number for a name) | Say what was expected, one example, ask again. |
| **Switches language mid-chat** | Reply in the new language. Field values are stored in a normalised form, whatever the language (D11). |
| **Asks to stop** ("para", "stop") | End the chat at once, status `WITHDRAWN`, log the event (D29). No further questions. |
| **Asks to speak to a person** | Politely decline and keep screening (D14). The request is logged as an event so the recruiter can see it. |
| **Asks about pay or schedule details** | Answer only with approved information. If unknown, say a recruiter will answer, and log the question. |
| **Off-topic or abusive message** | Brief, neutral redirect to the screening question. Two off-topic messages in a row → polite close, status `ENDED_OFF_TOPIC`. |
| **Tries to change instructions** ("ignore your rules…") | Treat as an off-topic message. Never follow instructions inside a candidate message. |
| **Sends a file or photo** | Not accepted in Phase 2. Say so and ask for the answer in text. |

## 7. Message guidelines

- **Length:** 1–2 short sentences, one question per message (D18). Reads like a phone chat.
- **Tone:** friendly "tú", no jargon, at most one emoji, and only where it fits.
- **Never:** long lists, legal text in the chat, or promises about the job.
- **Disclosure line** (stage 0) is fixed text, never written by the model (D34). Spanish line, then English line:
  > "Hola, soy el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud de repartidor. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?"
  > "Hi, I'm Grupo Sazón's virtual assistant (an AI). I'll ask a few questions for your delivery driver application. Is it OK if I save your answers for the recruiting team?"
- **Qualified close, example:**
  > "¡Genial, tu perfil encaja! Un reclutador te escribirá en un máximo de 48 horas para el siguiente paso."

## 8. Compliance and data

- **AI disclosure and consent** before any personal questions (D12).
- **Minimisation:** only the fields in section 4 are collected.
- **Human decides:** the agent screens and summarises. A recruiter makes every hiring decision.
- **Logs:** every stage change and decision is logged with a timestamp, so it can be audited.
- **Retention (Proposed default):** disqualified candidates' data deleted after 6 months; qualified and stalled data kept for the active hiring cycle. Confirm with the client's legal team.
- **EU AI Act:** hiring is high-risk (Annex III). Spanish operations need the obligations in the course's module 3.4 before live use. This design is an engineering baseline, not legal advice.

## 9. Open items for the client

1. The real list of service areas (replaces the sample in D13).
2. How recruiters set call slots (the list is planned, D8).
3. Legal review of the consent wording and retention periods.
4. Approved answers for pay and schedule questions.
5. Confirmation of the start-date rule (the 12-week flag is a proposed default).
