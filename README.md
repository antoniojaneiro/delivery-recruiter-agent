# delivery-recruiter-agent
An AI-powered candidate screening agent for a fictional client that has a restaurant chain and is hiring delivery drivers.

## Run it

```
python -m pip install -e ".[dev]"
copy .env.example .env      # Windows (use cp on macOS/Linux), then add your GEMINI_API_KEY; never commit .env
python -m sazon.chat        # terminal chat; commands: /new, /resume <id>, /wait24h, /quit
python -m sazon.chat --list-models   # if the default model name returns 404
python -m pytest -q         # unit tests, no network
python -m pytest -m live -q # real-model checks, needs the key; use fictional data only
```

Design: [PHASE1_PROCESS_DESIGN.md](PHASE1_PROCESS_DESIGN.md). Decisions: [DECISIONS.md](DECISIONS.md).
