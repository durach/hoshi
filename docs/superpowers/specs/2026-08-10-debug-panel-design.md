# Debug panel — design

**Date:** 2026-08-10
**Status:** approved, not implemented

## The problem

Hoshi sometimes reports a mistake that is not there. Three cases observed in one
day of ordinary use:

| id | what Hoshi claimed | what the text actually said |
|----|--------------------|-----------------------------|
| 13 | "Use the past participle *decided* after *have*" | already `have decided` |
| 14 | "*false positive* needs the article *a* in both occurrences" | the first occurrence already had `a` |
| 32 | "*Very bottom* needs the article *the*" | already `at the very bottom` |

Every one is the same failure: **the model asserts that a function word is
missing when it is already present**, then "corrects" the text to what it
already said and marks the unchanged word. Never a wrong fix — always an
imagined absence. Three of 22 stored results with a correction carry at least
one such span.

`id=32` is the interesting one. Four of its five findings are genuine
(`adjutment`→`adjustment`, `account`→`an account`, `in`→`with`, `ebe`→`be`);
only the fifth is invented. So the cheap rule — *if the correction is identical
to the original, discard everything* — does not fire on it at all. Detection has
to work per marked span, not per result.

Diagnosing any of this is currently guesswork. `_run_check` keeps the finished
`GrammarResult` and discards everything else: the raw model response, the model
id, the latency. `build_result` also silently drops findings whose type is not
in `ISSUE_TYPES`, leaving no trace that they existed.

## Goals

- Make any past check inspectable, without reproducing it.
- Detect marked spans that changed nothing, and show them.
- Change nothing about what the dashboard reports.

## Non-goals

Deliberately excluded, each its own decision later:

- **Acting on the analysis.** Nothing is suppressed, downgraded or hidden. The
  point of surfacing first is to learn whether the detector is trustworthy
  before letting it change a verdict.
- **Re-running a prompt**, against the same model or another one.
- **Editing `SYSTEM_PROMPT` from the browser.**
- **Naturalness suggestions** — the separate question of Hoshi saying too
  little, which the `style` cap currently suppresses by design.
- **A local LLM provider.**

## Design

### 1. Capture

`CheckResult` gains `debug: dict | None`, populated on every check.

```json
{
  "request": {
    "provider": "openai",
    "model": "gpt-5.6-terra",
    "system_prompt_hash": "a3f1c2e8"
  },
  "raw": { "issues": [...], "correction": "..." },
  "derived": { "dropped_issues": [{"type": "clarity", "note": "..."}] },
  "timing": { "latency_ms": 1412, "usage": {"input": 512, "output": 98} },
  "analysis": {
    "no_op": false,
    "ghost_marks": [{"text": "the", "type": "grammar", "offset": 381}],
    // offset is into the tag-stripped correction, so the client can locate the
    // span without re-parsing the markup
    "diff": [
      {"op": "equal", "before": "…", "after": "…"},
      {"op": "replace", "before": "adjutment", "after": "adjustment"}
    ]
  }
}
```

`system_prompt_hash` rather than the prompt text: it is 2.3 KB and identical
across every result in a run, so storing it per result would waste megabytes to
say the same thing 1000 times. The hash answers the only question worth asking
of a stored result — *was this produced by the same prompt as that one?* The
text itself is served once, from its own endpoint.

`raw` is what the provider returned **before** `build_result` normalises it.
`derived.dropped_issues` records what normalisation removed, so the gap between
raw and displayed is explicit rather than inferred.

On the error path, `debug` holds the exception type and any raw text received.
Today a provider failure yields `"Grammar check failed: {e}"` and nothing else.

Capture is unconditional — not behind an env var. A debug mode you must enable
before the interesting result arrives cannot help with the interesting result,
and these cases do not reproduce reliably. Cost is a few KB per result, a few MB
at the 1000-result cap.

### 2. Ghost-mark analysis

A new `backend/analysis.py`: pure functions, no I/O, no provider knowledge.

```
strip <mark> tags from the correction, recording each span's offset
tokenise the original and the stripped correction into whitespace-separated words
difflib.SequenceMatcher over the two word lists
changed := word indices covered by a `replace` or `insert` opcode
a mark is a ghost when it overlaps at least one word and none of them changed
```

This is a **heuristic**, and the UI must word it as one: *"this span appears
unchanged"*, never *"the model was wrong"*. Word alignment is reliable for the
short prompts Hoshi sees, but on a heavily rewritten multi-paragraph correction
`difflib` can align badly and call a real change a ghost. Nothing acts on the
result, so a wrong call costs a raised eyebrow — but the wording matters if this
is ever promoted to suppressing findings.

The same module also emits a **word diff** — the opcodes `difflib` already
computed, flattened into `{op, before, after}` segments. The browser renders it
rather than diffing anything itself: Python has the algorithm, and a second
implementation in JavaScript would be a second thing to keep correct. For
`id=13` the diff is a single `equal` segment covering the whole text, which
shows at a glance that nothing changed.

`no_op` — the stripped correction equals the original, ignoring leading and
trailing whitespace — is recorded separately.
It is strictly weaker than the per-span check, but it is exact rather than
heuristic, so it is worth reporting on its own.

### 3. API

- `GET /api/results/{id}/debug` — the captured dict. Bearer auth, as
  `/api/results`. 404 for an unknown id. Ids are unique only within a run, so
  this resolves against the current run's store, which is the only one there is.
- `GET /api/debug/system-prompt` — the text and its hash.
- `debug` is **excluded** from `CheckResult.to_dict()`, so `/api/results` and the
  WebSocket payload stay the size they are now. Debug is fetched when a panel is
  opened, not broadcast to every client on every check.
- One exception: `to_dict()` gains a derived `has_ghost_marks` boolean. The
  entry marker has to be decidable from the broadcast payload — otherwise
  turning debug on would fire one request per visible entry just to learn which
  ones to mark. A single bool is not the thing the exclusion was protecting
  against.

### 4. Dashboard

A **debug toggle in the header**, beside the theme switch, persisted in
`localStorage` the same way, off by default. With it off the dashboard is
unchanged in every respect.

With it on:

- Each entry header gains a small `debug` link; clicking fetches that result's
  debug payload and expands a panel inline.
- Entries whose analysis found a ghost span carry a small marker, so a bad
  result is noticed rather than stumbled upon. Under the toggle only — the
  normal view stays as it is.

Panel contents, ordered by what gets looked at first:

1. **Analysis.** *"1 marked span appears unchanged: `the`"*, or *"correction is
   identical to the original"*. First, not buried under a JSON dump.
2. **Word diff** — original against correction, showing what actually changed
   versus what was merely marked.
3. **Request line** — `openai · gpt-5.6-terra · prompt a3f1c2 · 1.4s · 512 in / 98 out`.
4. **Raw JSON**, pretty-printed and scrollable. Last: by the time it is wanted,
   the reader already knows what they are looking for.

## Testing

Against `analysis.py`'s pure functions, so no network and no provider mocks:

- **The three real cases**, verbatim from the store. `id=13` (total no-op),
  `id=14` (one bogus `a` among two genuine fixes), `id=32` (one bogus `the`
  among four). `id=32` is the one that distinguishes per-span alignment from the
  blanket rule, so it is the most valuable of the three.
- **The inverse**: a correct multi-fix correction reports zero ghosts. A
  detector that cries wolf on good results is worse than no detector.
- **Awkward marks**: spanning several words, containing punctuation, adjacent to
  each other, an empty correction, a correction with no marks at all.
- **Endpoint**: auth required, 404 on unknown id, and `debug` absent from
  `to_dict()`.
- **Error path**: a provider raising mid-check still yields a result whose debug
  holds the exception type.

## Risks

- **Alignment heuristic** — mitigated by wording, by acting on nothing, and by
  the cry-wolf test above.
- **Memory** — bounded by the existing 1000-result cap.
- **Token usage varies by SDK.** OpenAI reports it plainly; the other two differ.
  The field stays optional rather than complicating the shape for all three.

## Follow-ups

Noted, not scheduled:

- Promote ghost detection from an observation to a guard, once its rate of false
  alarms is known.
- Re-run a stored prompt against the same or another model.
- The corrected text renders through markdown while the prompt does not, so a
  line beginning `+` shows as a literal `+` above and a bullet below, making the
  before/after harder to compare by eye.
