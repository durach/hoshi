# Ollama structured-output spike — findings

Date: 2026-08-17

## Question

Does Ollama's OpenAI-compatible `/v1` endpoint honor strict
`response_format: json_schema` for `GRAMMAR_SCHEMA`? This gates the rest of
the named-checkers plan (Tasks 2–9 assume "no fourth provider" — Ollama can
be driven through the existing OpenAI provider path).

## Environment

- Ollama installed via `brew install ollama` (not previously present on this
  machine).
- Version: `0.32.14` (`curl -s http://localhost:11434/api/version` →
  `{"version":"0.32.14"}`).
- Started via `brew services start ollama`.
- Model: `qwen3:4b`, pulled with `ollama pull qwen3:4b` (~2.5 GB, single
  layer `3e4cb1417446`).

## Step 2: real provider path, strict json_schema

Ran the spike script from the brief verbatim (written to a scratch path
outside the repo), executed with the project venv's Python interpreter, cwd
= worktree repo root so `sys.path.insert(0, "backend")` resolves, importing
the **unmodified** `backend/providers` module — `GRAMMAR_SCHEMA`,
`SYSTEM_PROMPT`, `build_result`, `parse_provider_json` — and constructing the
OpenAI SDK client exactly as a future `OllamaProvider` would:

```python
client = openai.AsyncOpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
resp = await client.chat.completions.create(
    model="qwen3:4b",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": PROMPT},
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "grammar_check", "strict": True, "schema": GRAMMAR_SCHEMA},
    },
)
```

Fixed spike prompt (synthetic, from the brief — not a live dashboard
result):

```
i has been working on this all morning and the tests still dont pass
```

Result: **no API error**. The response parsed cleanly as JSON (no prose
wrapper), `issues` used only enum-valid `type` values, and `correction`
carried well-formed `<mark data-type="...">` tags.

Two runs, sample output (both synthetic, both from the fixed prompt above):

Run 1:
```
issues: [{'type': 'grammar', 'note': "Subject-verb agreement: 'i' requires the verb to be 'have' not 'has'."}, {'type': 'spelling', 'note': "'dont' is misspelled; it should be 'don't'."}]
correction: i <mark data-type="grammar">have</mark> been working on this all morning and the tests still <mark data-type="spelling">don't</mark> pass
dropped: []
```
Latency: 3m 07.8s wall (`time` on the whole process — includes first-load of
the model into memory).

Run 2 (immediately after, model presumably still resident):
```
issues: [{'type': 'grammar', 'note': "The verb 'has' should be 'have' for the first person singular subject 'I'."}, {'type': 'punctuation', 'note': "The contraction 'dont' is missing an apostrophe."}]
correction: i <mark data-type="grammar">have</mark> been working on this all morning and the tests still <mark data-type="punctuation">don't</mark> pass
dropped: []
```
Latency: 2m 09.0s wall.

Both runs are well-formed, schema-conformant JSON with no retry needed.
Note the model classified the `dont` fix as `spelling` in run 1 and
`punctuation` in run 2 — mark-type choice is not perfectly stable across
runs, but every value produced was a valid member of the type enum both
times, and `dropped_issues` was empty both times (i.e. `build_result` never
had to discard anything malformed). Latency is high relative to the cloud
providers (~2–3 minutes on this machine's CPU inference for a 4B model,
even on the second, presumably-warm run) — worth flagging for Task design
around timeouts, but out of scope for this go/no-go.

## Step 3: container reachability

From the **main checkout** (not the worktree — this is where the `hoshi`
compose project lives), with the existing `hoshi-backend-1` /
`hoshi-frontend-1` containers already up:

```
$ docker compose -p hoshi exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5).read())"
b'{"version":"0.32.14"}'
```

The backend container reaches the host's Ollama via `host.docker.internal`
without any extra Docker Desktop configuration.

## Verdict: GO

Strict `response_format: json_schema` is honored by Ollama's OpenAI-compat
endpoint for `qwen3:4b` against `GRAMMAR_SCHEMA`, driven through the
unmodified provider helpers (`build_result`, `parse_provider_json`) and the
same OpenAI SDK client construction the plan intends to reuse. No prose
wrapping, no malformed JSON, no `response_format` rejection. The container
reaches the host's Ollama over `host.docker.internal:11434` with no
additional Docker configuration. "No fourth provider" holds — Ollama can be
added as a model/base_url variant of the existing OpenAI-compatible
provider path rather than requiring a bespoke `OllamaProvider` on Ollama's
native `format` field.

Caveats for follow-on tasks (not blockers):
- Latency (~2–3 min per check on this machine, CPU inference) is much
  higher than the cloud providers; timeout/UX handling should account for
  this.
- Mark-type classification for the same input was not identical between
  two consecutive runs, though always enum-valid — ghost-mark analysis
  remains observe-only per the existing design, so this doesn't change any
  verdict logic.
