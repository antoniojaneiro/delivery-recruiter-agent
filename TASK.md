# TASK: FDE Technical Assignment: Candidate Screening Agent

Source: Notion page "FDE Technical Assignment" (copied from the pasted brief).

## Overview

Build an AI-powered candidate screening agent for a fictional client. This assignment evaluates your ability to design a recruitment process, implement it as a conversational AI system, and present your work.

- **Time:** a few days or a weekend. Quality matters more than speed.

## The client: Grupo Sazón

A restaurant chain hiring delivery drivers.

| Detail | Info |
| --- | --- |
| Locations | 45 across Spain and Mexico |
| Applications | ~1000/week |
| Current process | 13 recruiters, manual phone screening (~15 calls/day each) |
| Problems | 60% of candidates don't answer calls. 80% of recruiter time goes to unqualified candidates |

## Screening criteria

The agent must collect and validate:

| Field | Validation |
| --- | --- |
| Full name | Required |
| Driver's license | Yes/No. Disqualify if No |
| City / zone | Must be within service areas |
| Availability | Full-time, part-time, weekends |
| Preferred schedule | Morning, afternoon, evening, flexible |
| Prior delivery experience | Years + platform (Glovo, Uber Eats, etc.) |
| Start date | When can they begin |

## Phase 1: Process design

Before writing code, design the conversation flow. Deliver a **1-2 page document** covering:

- [ ] Conversation stages (order, branching logic)
- [ ] Agent personality
- [ ] Data fields + validation rules
- [ ] Edge cases:
  - Candidate stops responding mid-conversation
  - Invalid or ambiguous answers
  - Candidate switches language (Spanish <-> English)
- [ ] Qualified vs. disqualified paths (what happens at each outcome)
- [ ] Message tone and length guidelines (this is messaging, not email)

## Phase 2: Build

We want a product recruiters can start using. Only two things are expected:

1. A conversational agent that screens candidates.
2. A tool for recruiters to keep track of candidates.

### Core requirements

| Requirement | Detail |
| --- | --- |
| Language | Python |
| LLM | Your choice (justify it) |
| Conversation | Natural dialogue following the Phase 1 design |
| Data extraction | Structured JSON output with all screening fields |
| Validation | Reject invalid inputs gracefully, ask again |
| Context | Maintain full conversation history |
| Storage | Save conversations + extracted data as JSON or in DB |
| Summary | Generate a post-conversation summary with key data points |
| Error handling | Graceful failures, no crashes on unexpected input |

### Bonus: voice agent

| Requirement | Detail |
| --- | --- |
| Voice interaction | Browser-based voice agent (e.g. ElevenLabs or similar) |
| Same flow | Handles the same screening process via voice |

### Other bonus features

The brief says "pick any that interest you, other ideas are welcome", but the list in the source was empty. Ask the user for the list if it matters.

## Deliverables

- Phase 1 process design document (1-2 pages).
- Phase 2 code: the screening agent and the recruiter tracking tool.
- Presentation of the work (the brief says "present your work"; format not specified yet).
