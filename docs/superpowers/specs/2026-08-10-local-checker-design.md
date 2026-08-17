# Local checker and second opinions — design in progress

**Date:** 2026-08-10
**Status:** resolved — the open question was decided on 2026-08-15 (option A);
see [2026-08-15-checkers-config-design.md](2026-08-15-checkers-config-design.md)

This design was started in a session that was forked and then closed. Recovered
from its transcript so the decisions below are not re-litigated.

## Why

Three motivations, in the order they were given:

1. **Privacy** — every prompt typed into any agent currently goes to OpenAI.
2. **Cost** — the running per-check spend.
3. **Adoption** — the repo is public, and *"a lot of people probably won't pay
   money for tokens for this thing"*. A local option is the on-ramp: clone, run,
   see it work, then decide whether an API key is worth it.

## Decided

- **Local is one of the options, not the default.** Cloud stays first-class;
  local sits beside it.
- **Ollama on the host**, backend reaches it at `host.docker.internal:11434`.
  Not in the compose stack: Docker Desktop on macOS has no GPU passthrough, so
  an in-container model would be CPU-only on exactly the machines this is meant
  to attract.
- **Comparison is retrospective — option (c).** An existing result gets a
  "check with…" control; the second opinion appears inside the same entry. Not
  every prompt through both (doubles spend, against motivation 2), and not a
  separate offline eval script.
- **The second opinion lives on the result** in the existing in-memory store.
  Survives a reload within a run, dies on restart like everything else. No new
  persistence layer — that remains a deliberate non-goal.

## Open question — resume here

Config today is a single `PROVIDER` + `MODEL` pair. Retrospective comparison
needs several available at once. Two shapes were on the table:

**A. A named list of checkers**, probably a `checkers.json` beside
`tokens.json`, since this is more structure than a flat `.env` holds:

```json
[
  {"name": "cloud",     "provider": "openai", "model": "gpt-5.6-terra", "default": true},
  {"name": "local",     "provider": "ollama", "model": "qwen3:8b"},
  {"name": "local-big", "provider": "ollama", "model": "qwen3:30b"}
]
```

Buys: comparing **model tiers**, not just vendors — which is what you actually
want the moment the first local model disappoints. The hook and composer paths
have to say which checker ran.

**B. One primary plus one designated "compare against"**, two env vars. Less
config, but changing the local model means editing `.env` and restarting — and
restarting clears the store, losing the very result you were comparing.

## What changed under this design while it was paused

Work merged on 2026-08-10 that this should build on rather than duplicate:

- Every result already records `debug.request.provider` and
  `debug.request.model`. Per-result provenance exists; a second opinion needs a
  place to put a *second* one, not a new mechanism.
- `backend/analysis.py` is provider-agnostic. Ghost detection and the word diff
  work on any checker's output, so **comparing how often each model invents a
  finding is nearly free** once two can run.
- The dashboard renders a diff rather than a corrected paragraph, so a
  side-by-side view compares two diffs, not two paragraphs.
- The agent label already demonstrates the pattern for "which thing produced
  this", validated at three points before it becomes a CSS class.

## Constraint carried over

Whatever runs locally must enforce `GRAMMAR_SCHEMA` the way the three cloud
providers do — OpenAI strict `json_schema`, Anthropic a forced tool call, Gemini
`response_schema`. Ollama supports a JSON schema in its `format` field; if that
proves weaker in practice, the guarantee weakens rather than moves, and the
`<mark>` discipline is the part most likely to suffer on a small model.
