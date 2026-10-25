# Phase 1: Process design — driver screening agent (Grupo Sazón)

Status: draft for review. Every choice traces to [DECISIONS.md](DECISIONS.md) (D1–D48). Items marked *proposed default* need the client's confirmation.

## 1. Purpose

Screen delivery-driver applicants by chat so recruiters only speak to qualified candidates. Today 60% of candidates don't answer calls and 80% of recruiter time goes to unqualified applicants. The agent screens and summarises; **a recruiter makes every hiring decision**. Phase 2 runs in the terminal, and a real messaging channel comes later (D1).

## 2. Agent personality

- An AI assistant for Grupo Sazón recruiting, and it says so in its first message.
- Warm and direct, friendly "tú" (D15). Patient, never pushy, never judgmental.
- Replies in the candidate's language, Spanish or English, and switches when they do (D11).
- Never promises a job or pay, never decides, never invents call times.

## 3. Conversation stages

| Stage | What happens | Exit |
| --- | --- | --- |
| **0. Consent** | Fixed bilingual AI disclosure and consent to store answers. The reply is read in plain code, so nothing reaches the model before a yes (D12, D34, D44). | Clear no or "stop" → polite close `NO_CONSENT`. Clear yes → stage 1. Unclear → ask again. |
| **1–5. Name, experience, availability, schedule, start date** | One question at a time, in a friendly order (D6). If a message answers later fields, they are recorded and not asked again (D5). | Valid → next. Unclear → follow-up (below). |
| **6–7. City, driver's license** | Eligibility, checked as soon as answered (D27). | In area / license yes → next. Outside area or no license → one confirmation question, so one misread never rejects anyone (D40), then a polite close. |
| **8. Decision** | See section 5. | |

**Follow-ups (D41).** An unclear answer gets up to 5 follow-ups, each saying the information is needed to move forward. Then the agent says it cannot continue until the field is provided, and repeats that to every later message. The candidate is `BLOCKED` on that field until it is answered.

## 4. Data fields and validation

| Field | Accepted input | Rule |
| --- | --- | --- |
| Full name | Text | At least two words of letters, hyphens or apostrophes (García-López, O'Brien). |
| Driver's license | Yes / no | No → `NO_LICENSE` (after confirmation). "Unsure" → ask again. |
| City / zone | Text | Fuzzy match to the service-area list (sample list for now, D13). Unsure → "¿Te refieres a Guadalajara?". Not listed → `OUT_OF_AREA`. |
| Availability | Full-time, part-time, weekends | One or more. |
| Preferred schedule | Morning, afternoon, evening, flexible | One. |
| Experience | Years (number, "ninguna") and platform (Glovo, Uber Eats, other) | Years ≥ 0. Recorded, never disqualifies (D19). |
| Start date | "ya", a date, "en N semanas" | Converted to a date in code. Past is invalid. More than 12 weeks away is recorded and flagged (*proposed default*). |

Only validated values are stored (data minimisation).

## 5. Outcomes: qualified and disqualified paths

| Outcome | When | What the candidate hears | What the recruiter gets |
| --- | --- | --- | --- |
| **Qualified** | All fields, license yes, city in area. | The next three free call slots of their country, numbered. A pick books it (D7, D8, D48). "None", or no free slot: "a recruiter will reply within 48 hours". | Summary card and the booking. |
| **Disqualified** | `NO_LICENSE`, `OUT_OF_AREA`, `NO_CONSENT`. | Polite close with the reason in one sentence; they may apply again (D9). | Reason and card. |
| **Blocked** | A field still unclear after 5 follow-ups. | "I can't continue until you tell me X." | `BLOCKED` naming the field. |
| **Stalled** | 24 h of silence: one reminder; 24 h more: `STALLED`. A new message resumes (D10, D35, D38). | One short reminder. | `STALLED`, last stage. |
| **Withdrawn / off topic** | The candidate asks to stop (D29), or sends two off-topic messages in a row. | A polite close, no more questions. | `WITHDRAWN` or `ENDED_OFF_TOPIC`. |

## 6. Edge cases

| Situation | Behaviour |
| --- | --- |
| **Stops responding mid-chat** | One reminder at 24 hours, then `STALLED`; the chat resumes if they write again. |
| **Vague or invalid answer** ("a veces", "no sé" for a date) | Say what is expected, with an example, and ask again. Counts toward the 5 follow-ups. A model failure never counts (D39). |
| **Switches language (ES ↔ EN)** | Reply in the new language; values are stored in one normalised form. An unsupported language keeps the last supported one. |
| **Asks to speak to a person** | Politely declined, screening continues, and the request is logged for the recruiter (D14). |
| **Asks about pay or schedule** | Handled as an off-topic message for now; the client must supply approved answers (open item). |
| **Off-topic, abusive, or "ignore your rules"** | A neutral redirect; two in a row end the chat. Candidate text is data, never instructions. |
| **Sends a file or photo** | Text only in Phase 2. |

## 7. Message guidelines

- This is messaging, not email: 1–2 short sentences and one question per message (D18); friendly "tú"; at most one emoji; no jargon or legal text. The numbered slot list is the one exception.
- The disclosure and the closes are fixed text, never written by the model (D34, D37):
  > "Hola, soy el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud de repartidor. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?"
  >
  > "¡Genial, tu perfil encaja! Elige una hora para una llamada corta con el equipo: 1) mar 3 nov, 10:00 2) mié 4 nov, 09:30 3) jue 5 nov, 16:00. Responde con el número, o 'ninguna' y un reclutador te escribirá en un máximo de 48 horas."

## 8. Compliance and open items

- Hiring is high-risk under the EU AI Act (Annex III), and Mexico has its own data law. The design therefore has: AI disclosure and consent first (D12); human oversight; every stage change and decision logged with time and actor; no emotion or personality inference; and untrusted candidate text. This is an engineering baseline, not legal advice.
- **Retention** (*proposed default*): disqualified data deleted after 6 months; other data kept for the active hiring cycle.
- **Open items for the client:** the real service areas; legal review of the consent wording and retention; approved answers for pay and schedule questions; confirmation of the 12-week start-date rule; recruiter login (the prototype has none).
