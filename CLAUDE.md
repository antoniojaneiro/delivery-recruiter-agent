# CLAUDE.md

Guidance for Claude Code in this repo. The assignment itself is in [TASK.md](TASK.md). Read it first.

## What we're building

A candidate screening agent for Grupo Sazón (fictional): a restaurant chain hiring delivery drivers across Spain and Mexico. The deliverables are:

1. **Phase 1:** a 1-2 page process design. Draft in [PHASE1_PROCESS_DESIGN.md](PHASE1_PROCESS_DESIGN.md). Its unconfirmed defaults are listed in [DECISIONS.md](DECISIONS.md). Phase 2 has not started.
2. **Phase 2:** a Python conversational agent that screens candidates, plus a recruiter tool to track candidates.
3. **Bonus:** a browser voice agent that runs the same flow.

## Workflow (always follow, in this order)

1. **Create a branch from `main`** for each piece of work. Never work directly on `main`.
2. **Grill me to make a plan** of what we will build, using the `grill-me` interview style. Give options with pros, cons and a recommendation. Get my answers before building.
3. **Build with TDD** (the `tdd` skill): failing test first, then the code, then refactor.
4. **Ask whether I want an architecture review** (`improve-codebase-architecture`) after each piece of work. Always say when the last one was, in commits: run `git rev-list --count <last-review-commit>..HEAD`. If none has happened yet, say that and count from the first commit.

### Model roles

- **Sonnet 5.5 builds:** directs the session and writes the code.
- **Haiku 5.5 explores:** file and documentation search, reading the course material, checking skills. Use an Agent subagent with `model: "haiku"` (Explore type) for broad searches, and run independent searches in parallel.
- **Opus 5.5 reviews:** the `advisor` tool, only at these points: before committing to a plan (after the grill), when an error recurs or the approach stops converging, and before declaring a piece of work done.
- Opus is not used for routine edits or lookups.
- The launch flags `claude --advisor opus --subagents haiku` come from a post. They are unverified here. If `claude --help` in your terminal confirms them, you can also start with them. The roles above work without the flags.

**Last architecture review:** 2026-10-25 at commit `1fb5be0` (whole product, four reviewers plus a real-model scenario run, D50). Its bugs and decisions were implemented afterwards (D51-D59); the structural findings from the slice 3 review (D49) are still open. 13 commits since, so a new review is due. Update this line each time a review happens.

## Decisions

All settled design and tech choices are logged in [DECISIONS.md](DECISIONS.md), with options, pros and cons. Before acting against an entry, say so and confirm with the user. Add new entries as decisions are made.

## Stack and decisions

- **Language:** Python.
- **Channel:** terminal chat first, real channel later (D1).
- **LLM:** Gemini free tier, through the course wrapper at `C:/Users/AJ/agent_engineering/Agentic-AI-Course/00-setup/course_llm.py` (D2).
- **Storage:** SQLite (D3).
- **Voice:** ElevenLabs is the suggested option (see the `agents` skill).
- **Recruiter UI:** Streamlit dashboard, run locally (D4). The course capstone uses Streamlit too, and the `developing-with-streamlit` skill covers it.

## Hard constraints (from the domain)

- **Hiring is high-risk under the EU AI Act** (Annex III, employment). Spain is in the EU. Mexico has its own data-protection law (LFPDPPP). Design for:
  - Human oversight: a recruiter always makes the final decision, and the agent only screens and summarises.
  - Logging of decisions and the data behind them.
  - Telling candidates they are talking to an AI.
  - Data minimisation: collect only the screening fields.
  - No emotion recognition or inference from voice or text.
- **Candidate messages and CVs are untrusted input.** Treat them as data and guard against prompt injection.
- **Secrets:** API keys live in a `.env` file that is never committed. Never copy keys from the course files into this repo.
- **Language:** candidates may write in Spanish or English and may switch mid-conversation.

## Conventions

- Use the `tdd` skill for building features and fixing bugs: write a failing test first.
- Use `python-testing-patterns` for pytest structure.
- Validation rules and the qualified/disqualified decision are pure functions with unit tests. The LLM only extracts and converses.
- Keep the conversation state, the extracted JSON and the summary as separate outputs.
- Messages are chat messages, not emails: short, one question at a time.
- Match the style of the code around you. Keep comments sparse.

## Skills installed in `.claude/skills/`

| Skill | Use it for |
| --- | --- |
| `grill-me` | Stress-testing the Phase 1 design. Only when asked. |
| `tdd` | Test-first development. |
| `python-testing-patterns` | pytest layout, fixtures, mocking the LLM. |
| `improve-codebase-architecture` | Reviewing structure after the first working version. Only when asked. |
| `agents` (ElevenLabs) | The voice agent bonus. Needs `ELEVENLABS_API_KEY` in `.env`. |
| `developing-with-streamlit` | The recruiter tracking UI (official Streamlit skill). |
| `find-skills` | Finding other skills on skills.sh. |

## Course material (reference, read-only)

The reference course is a private repo at `C:/Users/AJ/agent_engineering/`. It contains DataCouch training material. Read it for patterns and copy the ideas, not the files. Do not commit course content into this repo, and do not publish it.

Start with the course study plan: `C:/Users/AJ/agent_engineering/Agentic-AI-Course/STUDY_PLAN.md`. The root of the course is `C:/Users/AJ/agent_engineering/Agentic-AI-Course/`. Below, `COURSE` means that root. The course PDF `C:/Users/AJ/agent_engineering/ai-agents-complete-guide.pdf` is a general reference.

The course's domain is financial crime and HR ops (Northwind Hotels), not delivery hiring. Its patterns transfer. Its examples do not.

| I need to... | Read |
| --- | --- |
| Design the conversation flow, write the agent spec, plan discovery and pilot | `COURSE/part-3-fde-production/module-3.5-fde-craft/` (README, `templates/agent-spec-template.md`, `templates/discovery-questionnaire.md`, `templates/pilot-plan.md`, `templates/runbook-template.md`, `discovery_to_spec.ipynb`) |
| Understand EU AI Act, GDPR and fairness for hiring tools | `COURSE/part-3-fde-production/module-3.4-eu-ai-act-gdpr-fairness/README.md` and `fairness_audit.ipynb` |
| Check guardrails, prompt injection and red-teaming | `COURSE/part-3-fde-production/module-3.2-security-guardrails/` |
| Build the MCP / ATS integration, webhooks, idempotency, a FastAPI service | `COURSE/part-3-fde-production/module-3.1-mcp-and-enterprise-integration/code/` (`agent_service.py`, `ats_mcp_server.py`, `mock_ats_api.py`, tests) |
| Structured output, Pydantic contracts, spec-driven agents | `COURSE/part-2-advanced/module-02-spec-driven-development/` (`lab_2a.ipynb`) |
| Closest case study: high-volume applicant screening for HR tech, with the recruiter UI, HITL and evals | `COURSE/part-3-fde-production/module-3.6-study-kit/system-design-cases.md` (Case 1) |
| Pattern for an agent without a framework: raw tool-calling loop, structured output | `COURSE/part-3-fde-production/module-3.0-refresher-agents-without-frameworks/` |
| Build the conversation as a state graph (stages, branching) | `COURSE/part-1-foundations/module-04-agent-architectures-langgraph/` (`01-build-a-simple-graph.ipynb`, `02-langgraph_101.ipynb`) |
| Human review of edge cases (approve, reject, edit) | `COURSE/part-1-foundations/module-08-human-in-the-loop/` |
| Conversation memory and history | `COURSE/part-1-foundations/module-06-memory-context-rag/03-agent-memory.ipynb` and `COURSE/part-1-foundations/module-09-evaluation-finetuning-context-engineering/02-context-engineering.ipynb` |
| Evaluate the agent (eval sets, judges, cost-weighted errors) | `COURSE/part-3-fde-production/module-3.3-evals-from-customer-data/` and `COURSE/part-1-foundations/module-09-evaluation-finetuning-context-engineering/01-evaluating-llms.ipynb` |
| Regression tests and CI gate for the agent | `COURSE/part-2-advanced/module-07-enterprise-genai-sdlc/lab_7b.ipynb` |
| PII masking, cost budgets, observability | `COURSE/part-2-advanced/module-07-enterprise-genai-sdlc/lab_7a.ipynb` |
| A Streamlit app for the recruiter view | `COURSE/part-1-foundations/module-10-capstone-aml-detection/app.py` |
| LLM provider setup | `COURSE/00-setup/PROVIDERS.md` and `COURSE/00-setup/course_llm.py` |
| Practice Q&A and system-design answers | `COURSE/part-3-fde-production/module-3.6-study-kit/` |

The course `.env` holds real keys. Never open it or copy values from it.
