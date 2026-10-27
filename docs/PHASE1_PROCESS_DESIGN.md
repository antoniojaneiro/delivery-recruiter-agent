# Phase 1: Process design — driver screening agent (Grupo Sazón)

Status: draft for review. Every choice traces to [DECISIONS.md](DECISIONS.md) (D1–D59). *Proposed default* = to confirm with the client.

## 1. Purpose

Screen delivery-driver applicants by chat so recruiters only speak to qualified candidates. Today 60% of candidates don't answer calls and 80% of recruiter time goes to unqualified applicants. The agent screens and summarises; **a recruiter makes every hiring decision**. Phase 2 runs in the terminal; a real messaging channel comes later (D1).

## 2. Agent personality

- An AI assistant for Grupo Sazón recruiting; it says so in its first message.
- Warm and direct, friendly "tú" (D15). Patient, never pushy, never judgmental.
- Replies in the candidate's language, Spanish or English, and switches when they do (D11).
- Never promises a job or pay, never decides, never invents call times.

## 3. Conversation stages

| Stage | What happens | Exit |
| --- | --- | --- |
| **0. Consent** | Fixed bilingual AI disclosure, naming the external AI service, and consent to store answers. The reply is read in plain code: nothing reaches the model before a yes (D12, D44, D51). | Clear no or "stop" → close `NO_CONSENT` (a later "sí" restarts). Clear yes → stage 1. Unclear → ask again. |
| **1–5. Name, experience, availability, schedule, start date** | One question at a time, friendly order (D6). Later fields given early are recorded, not asked again (D5). A different value for an accepted answer is confirmed first (D54). | Valid → next. Unclear → follow-up. |
| **6–7. City, driver's license** | Eligibility, checked as soon as answered (D27). | OK → next. Outside area / no license → one confirmation question so a misread never rejects anyone (D40), then a polite close. |
| **8. Decision** | See section 5. | |

**Follow-ups (D41).** An unclear answer gets up to 5 follow-ups, each saying the information is needed. Then the agent says it cannot continue until it is provided, and repeats that: the candidate is `BLOCKED` on that field.

## 4. Data fields and validation

| Field | Accepted input | Rule |
| --- | --- | --- |
| Full name | Text | Two or more words of letters, hyphens, apostrophes; a dot after a title or initial is fine. |
| Driver's license | Yes / no | No → `NO_LICENSE` (after confirmation). "Unsure" → ask again. |
| City / zone | Text | Fuzzy match to the service areas, nearby towns and "Madrid, España" included (sample list, D13). Unsure → "¿Te refieres a Guadalajara?". Not listed → `OUT_OF_AREA`. |
| Availability | Full-time, part-time, weekends | One or more. |
| Preferred schedule | Morning, afternoon, evening, flexible | One. |
| Experience | Years (0–60) and platform (Glovo, Uber Eats, Just Eat, Rappi, DiDi Food, other) | Recorded, never disqualifies (D19). |
| Start date | "ya", a date, "en 2 semanas", "dentro de 3 meses", "el lunes" | Converted to a date in code; past is invalid; over 12 weeks away is flagged (*proposed default*). |

Only validated values are stored as the candidate's data; the conversation is kept as the audit record.

## 5. Outcomes: qualified and disqualified paths

| Outcome | When | What the candidate hears | What the recruiter gets |
| --- | --- | --- | --- |
| **Qualified** | All fields, license yes, city in area. | The next three free call slots of their country, numbered; a pick books it (D48). "None" or no slot: "a recruiter will reply within 48 hours". One reminder if ignored. | Summary card and the booking. |
| **Disqualified** | No license, or outside the area. | "I can't continue with the automated process; a recruiter can review your case" (D52). | Reason and card, in the **review queue** until a recruiter sets a status. |
| **Blocked** | A field unclear after 5 follow-ups. | "I can't continue until you tell me X." | `BLOCKED` naming the field. |
| **Stalled** | 24 h silent: one reminder; 24 h more: `STALLED`. A new message resumes (D58). | One short reminder. | `STALLED`, last stage. |
| **Withdrawn / ended** | The candidate asks to stop (D29), or sends a third off-topic message (D55). | Polite close. "continuar" resumes after a withdrawal (D56); the off-topic exit is final until a recruiter acts. | `WITHDRAWN` or `ENDED_OFF_TOPIC` (review queue). |

Candidates can come back while applications are open, except after qualifying, a rejection, or the off-topic exit. A dashboard switch stops everyone (D56).

## 6. Edge cases

| Situation | Behaviour |
| --- | --- |
| **Stops responding mid-chat** | One reminder at 24 hours, then `STALLED`; the chat resumes if they write again. |
| **Vague or invalid answer** ("a veces", "no sé" for a date) | Say what is expected, with an example, and ask again; counts toward the 5 follow-ups. A model failure never counts (D39). |
| **Switches language (ES ↔ EN)** | Reply in the new language; values are stored in one normalised form. An unsupported language keeps the last supported one. |
| **Asks for a person or about pay; goes off-topic; "ignore your rules"** | Person or pay: a fixed sentence (a recruiter reviews and answers), then the next question. Off-topic: "that's not part of my role" and the same question; the third in total ends the chat with a farewell about the messages, not the person (D55). Candidate text is data, never instructions. |

## 7. Message guidelines

- Messaging, not email: 1–2 short sentences and one question per message (D18); friendly "tú"; at most one emoji; no mid-chat greetings; no jargon or legal text. The numbered slot list is the one exception.
- The disclosure and the closes are fixed text, never written by the model (D34, D37):
  > "Hola, soy el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud de repartidor. Tus respuestas se procesan con un servicio de IA externo y siempre las revisa un reclutador. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?"
  >
  > "¡Genial, tu perfil encaja! Elige una hora para una llamada corta con el equipo: 1) mar 3 nov, 10:00 2) mié 4 nov, 09:30 3) jue 5 nov, 16:00. Responde con el número, o 'ninguna' y un reclutador te escribirá en un máximo de 48 horas."

## 8. Compliance and open items

- Hiring is high-risk under the EU AI Act (Annex III); Mexico has its own data law. Built in: AI disclosure and consent first, with the exact wording recorded; human oversight (review queue, D52); every decision logged with its actor; erasure on request, and nothing erased automatically (D53, D60); a login per recruiter (D57); no emotion or personality inference; untrusted candidate text. An engineering baseline, not legal advice.
- **Retention:** every conversation and its data are saved and kept. A recruiter erases one candidate only when they ask (D60); how long to keep the rest is a question for the client's lawyers.
- **Open for the client:** the real service areas; legal review of the consent and farewell wording and of how long data may be kept; approved answers about pay; the 12-week rule; single sign-on; a paid model tier with a data-processing agreement.
