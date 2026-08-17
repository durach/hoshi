# Named checkers and second opinions — design

**Date:** 2026-08-15
**Status:** decided (bead `hoshi-214`); resolves the open question in
[2026-08-10-local-checker-design.md](2026-08-10-local-checker-design.md)
**Depends on:** nothing. **Feeds:** result persistence (`hoshi-0ua`), the
ghost-rate eval (`hoshi-lli`).

## Decision

Checkers are a **named list in `checkers.json`**, mirroring the `tokens.json`
pattern: gitignored, a committed `.example`, loaded at startup, restart after
changes. The alternative — one primary plus one "compare against" in two env
vars — was rejected because changing the comparison model would mean editing
`.env` and restarting, and a restart clears the store, destroying the very
result being compared. A list also buys model-*tier* comparison (terra vs
qwen3:8b vs qwen3:30b), which is what the ghost-rate eval needs.

## The file

```json
{
  "checkers": [
    { "name": "terra", "provider": "openai", "model": "gpt-5.6-terra", "default": true },
    { "name": "luna",  "provider": "openai", "model": "gpt-5.6-luna" },
    { "name": "qwen8", "provider": "openai", "model": "qwen3:8b",
      "base_url": "http://host.docker.internal:11434/v1" }
  ]
}
```

Per checker: `name`, `provider`, `model`, optional `default` (bool), optional
`base_url`. No API keys — those stay in `.env`, keyed by provider as today.

Rules, enforced at startup so a config error kills the container instead of
surfacing as a 500 later:

- `name` is a slug (`[a-z0-9-]+`), unique across the list. It becomes a CSS
  class on the dashboard, so it is validated the way `agent` already is:
  in config at load, in the API request model, and once more client-side.
- **Exactly one `default: true`.** Zero or two is a startup error, never a
  silent choice. The default checker is what the hook's fire-and-forget path
  uses for every prompt; the others exist only for on-demand rechecks.
- `provider` must be one `create_provider` knows. Providers are constructed
  eagerly at startup, so a typo fails on boot.

**Fallback:** no `checkers.json` → synthesize a single default checker named
`default` from the existing `PROVIDER`/`MODEL` settings. Every current setup,
including the public quick start, keeps working unchanged.

## No fourth provider

Ollama serves an OpenAI-compatible API at `/v1`, so a local checker is the
existing `OpenAIProvider` plus two small changes:

- `create_provider` and `OpenAIProvider.__init__` accept `base_url`, passed to
  `AsyncOpenAI(base_url=...)`.
- When `base_url` is set and no OpenAI key is configured, the client gets the
  placeholder key `"ollama"` — the SDK requires a non-empty key; Ollama ignores
  it.

**Risk, unverified:** Ollama's compat layer must honor strict
`response_format: json_schema` for `GRAMMAR_SCHEMA`. Ollama is not installed on
the dev machine yet, so this is the implementation plan's first task: install,
pull a small model, run one check through the real provider path. If strict
mode is rejected, Ollama's native `/api/chat` accepts a JSON schema in its
`format` field, and a thin `OllamaProvider` becomes necessary — the config
shape survives either way, only the "no new provider" claim dies. The `<mark>`
discipline is the part most likely to suffer on a small model; that degrades
ghost detection (heuristic, observe-only), never the verdict.

## What changes where

- **`config.py`** — `checkers_file: str = "checkers.json"`.
- **new `checkers.py`** — load, validate, and construct: returns
  `dict[str, GrammarProvider]` plus the default's name. Pure enough to test
  with a fake factory.
- **`main.py`** — `app.state.checkers`, `app.state.default_checker`;
  `_run_check` takes a checker name, records it in the result and in
  `debug.request.checker`.
- **`store.py`** — `CheckResult.checker: str`, in `to_dict()`. Second opinions:
  `CheckResult.opinions: list[dict]`, each the same shape the entry already
  renders (`checker`, `issues`, `types`, `has_issues`, `diff`,
  `has_ghost_marks`, `elapsed_ms`), included in `to_dict()`. Opinion debug
  records go under the parent's `debug["opinions"][name]` — served by the
  existing debug endpoint, still never broadcast.
- **`POST /api/results/{id}/checks`** — body `{"checker": "<name>"}`, bearer
  auth. Runs that checker on the stored prompt, attaches the opinion,
  re-broadcasts the full result. 404 unknown id, 422 unknown checker or
  duplicate opinion.
- **frontend** — the dashboard already dedups by `(run_id, id)`; a re-broadcast
  of a known id **replaces the entry in place** instead of prepending. Each
  entry shows its checker name as a badge; a "check with…" control lists the
  non-default checkers not yet attached; an opinion renders as a second
  labelled diff block inside the same entry.
- **hook** — untouched. It never names a checker; the server applies the
  default.

## Out of scope

Per-checker temperature or prompt overrides (models in use reject
`temperature` anyway), parallel fan-out to all checkers (comparison is
retrospective by the 2026-08-10 decision), any UI for editing the list, and
persistence of opinions beyond the store's lifetime (that is `hoshi-0ua`).
