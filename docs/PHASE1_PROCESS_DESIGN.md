# Phase 1: Process design — driver screening agent (Grupo Sazón)

Status: updated to match the built agent. Choices trace to [DECISIONS.md](DECISIONS.md) (D-numbers). *Default* = to confirm with the client.

## 1. Purpose

Screen delivery-driver applicants by chat so recruiters only speak to qualified candidates. Today 60% of candidates don't answer calls and 80% of recruiter time goes to unqualified applicants. The agent screens and summarises; **a recruiter makes every hiring decision**. It runs in the terminal and in a browser chat; a real messaging channel comes later (D1).

## 2. Agent personality

The persona is written down once, for the model, and every free message follows it (D69):

- An AI assistant for Grupo Sazón recruiting, and it says so in its first message.
- Warm, direct and respectful, like a friendly recruiter on the phone; the informal "tú" in Spanish; patient, never pushy, never judgmental.
- Acknowledges what the candidate said in a few words, varies its wording, at most one emoji, no jargon.
- Never promises a job, pay or a call time, never states facts it was not given, never decides.

## 3. Conversation stages

| Stage | What happens | Exit |
| --- | --- | --- |
| **0. Consent** | Fixed bilingual AI disclosure naming the external AI service, and consent to store answers. The reply is read in plain code; nothing reaches the model before a yes (D12, D44). | Clear no or "stop" → close `NO_CONSENT` (a later "sí" restarts). Yes → stage 1. Unclear → ask again. |
| **0b. Optional CV** | Said once with the first question: "to go faster you can upload your CV as a PDF". An upload fills the clear answers for name, city, license and experience; the agent reads them back to be corrected. A value that would reject, or a near-miss place, is confirmed with the candidate first. Typing an answer instead skips it (D71). | Taken or skipped → stage 1. |
| **1–5. Name, experience, availability, schedule, start date** | One question at a time. Anything given early is recorded and not asked again (D5). A different value for an accepted answer is confirmed first (D54). | Valid → next. Unclear → follow-up. |
| **6–7. City, driver's license** | Eligibility, checked as soon as answered (D27). | OK → next. Outside the area or no license → one confirmation question, so a misread never rejects anyone (D40), then a polite close. |
| **8. Decision** | See section 5. | |

**Unclear answers (D41).** Up to 5 follow-ups, each saying what is needed. Then the agent says it cannot continue until it is provided, and the candidate is `BLOCKED` on that field.

## 4. Data fields and validation

| Field | Accepted | Rule |
| --- | --- | --- |
| Full name | Text | Two or more words of letters, hyphens, apostrophes; a title or initial with a dot is fine. |
| Driver's license | Yes / no | No → `NO_LICENSE` after confirmation. "No car" is not "no license". |
| City / zone | Text | Fuzzy match to the service areas, nearby towns and "Madrid, España" included (sample list, D13). Unsure → "¿Te refieres a Guadalajara?". Not listed → `OUT_OF_AREA`. |
| Availability | Full-time, part-time, weekends | One or more. "2 days a week" is part-time; weekends needs weekends, Saturday or Sunday. |
| Preferred schedule | Morning, afternoon, evening, flexible | One. |
| Experience | Years (0–60) and platform (Glovo, Uber Eats, Just Eat, Rappi, DiDi Food, other) | Never disqualifies (D19). Zero years only when the candidate says they have none; a plain "yes" is asked again. |
| Start date | "ya", a date, "en 2 semanas", "el lunes" | Converted to a date in code; past is invalid; over 12 weeks away is flagged (*default*). |

Only validated values are stored as the candidate's data (JSON); the conversation is kept as the audit record, and a Spanish summary card is built by code for the recruiter (D46).

## 5. Outcomes: qualified and disqualified paths

| Outcome | When | What the candidate hears | What the recruiter gets |
| --- | --- | --- | --- |
| **Qualified** | All fields, license yes, city in area. | The next three free call times of their country, numbered; a pick books it. None or no time: "a recruiter will reply within 48 hours" (D48). | Card and the booking. |
| **Disqualified** | No license, or outside the area. | "I can't continue with the automated process; a recruiter can review your case" (D52). | Reason and card, in the **review queue** until a recruiter sets a status. |
| **Blocked** | A field unclear after 5 follow-ups. | "I can't continue until you tell me X." | `BLOCKED` naming the field. |
| **Stalled** | 24 h silent: one reminder; 24 h more: `STALLED`. A new message resumes. | One short reminder. | `STALLED` and the last stage. |
| **Withdrawn / ended** | The candidate asks to stop (D29), or sends a third off-topic message (D55). | A polite close. "continuar" resumes after a withdrawal; the off-topic exit is final until a recruiter acts. | `WITHDRAWN` or `ENDED_OFF_TOPIC` (review queue). |

Candidates can come back while applications are open, except after qualifying, a rejection or the off-topic exit; a dashboard switch closes applications (D56).

## 6. Edge cases

| Situation | Behaviour |
| --- | --- |
| **Stops responding mid-chat** | One reminder at 24 hours, then `STALLED`; the chat resumes if they write again. |
| **Vague or invalid answer** ("a veces", "no sé" for a date) | Say what is expected, with an example, and ask again; counts toward the 5 follow-ups. A model failure never counts (D39). |
| **Switches language (ES ↔ EN)** | The chat follows the words the candidate writes, decided in code: a name, a place or a number never changes the language; a sentence in the other language does (D67). Values are stored in one form. |
| **Asks for a person or about pay; goes off-topic; "ignore your rules"** | Person or pay: a fixed sentence (a recruiter reviews and answers), then the next question. Off-topic: a short redirect; the third in total ends the chat with a farewell about the messages, not the person (D55). Candidate text is data, never instructions. |

## 7. Message tone and length

- Messaging, not email: 1–2 short sentences and one question per message (D18); no mid-chat greetings; no legal text. The numbered call list is the one exception.
- **Who writes what (D69).** The model words the questions, follow-ups, place confirmations, change questions and the "cannot continue" message in the voice above, seeing the recent conversation. Code checks every message (length, one question, language, no pay or time, the facts it must keep) and sends a fixed text if a check fails or the model is down. **Fixed word for word:** the disclosure, every closing, the call offers and bookings, reminders, the error line and the notices about a person, pay, a change made, an answer kept and an off-topic redirect.
  > "Hola, soy el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud de repartidor. Tus respuestas se procesan con un servicio de IA externo y siempre las revisa un reclutador. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?"

## 8. Compliance and open items

- Hiring is high-risk under the EU AI Act (Annex III) and Mexico has its own data law. Built in: AI disclosure and consent first, with the exact wording recorded; human oversight (review queue, a recruiter can overrule any status); every decision logged with its actor; erasure on request only, which also removes an uploaded CV (D53, D60, D71); a login per recruiter (D57); no emotion or personality inference; untrusted candidate text. Not legal advice.
- **Open for the client:** the real service areas; legal review of the consent and farewell wording, of sample conversations (the model's wording varies), of the CV notice, and of how long data (including CVs) may be kept; approved answers about pay; the 12-week rule; single sign-on; a paid model tier with a data-processing agreement.

## 9. Volume

About 1000 applications a week is roughly 6 an hour on average. Assuming a fifth of them arrive in the busiest 2 hours and each chat has about 10 messages, that is about 0.3 messages a second with 8 to 17 chats open. Nothing is kept in memory between messages, so several chats run at once; an HTTP service (D75) lets a channel start a candidate, send a message (a resent message gets the same answer) and collect queued messages. A load test with 200 candidates and a slow, failing fake model passed at about 25 times that peak (95% of replies within 5.5 s, no errors, nobody double-booked), and with all 200 arriving in the same instant every chat still ended correctly. The first limit reached is the database's single writer, at roughly 35 times the peak; the model's rate limit on a paid tier is the second.
