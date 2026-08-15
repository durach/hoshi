# Debug Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every grammar check inspectable after the fact, and surface marked spans that changed nothing.

**Architecture:** A pure `backend/analysis.py` compares the original text to the correction and reports spans the model marked but did not change. Every check stores a `debug` dict on its `CheckResult`, served from a new endpoint rather than broadcast. The dashboard gains a debug toggle that reveals a per-entry panel.

**Tech Stack:** Python 3.12, FastAPI, pytest, vanilla JS. No new dependencies — `difflib` and `hashlib` are stdlib.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-10-debug-panel-design.md`.
- **Nothing may change a verdict.** No finding is suppressed, reordered or hidden. `has_issues`, `types`, `issues` and `correction` must be byte-identical to what they are today.
- All backend commands run from `backend/`. Tests: `uv run task test`. Everything: `uv run task check` (ruff + mypy + pytest).
- The frontend has no build step and no test suite. Run `node --check frontend/static/app.js` before every frontend commit — a syntax error there kills the whole script while the page still renders enough to look fine.
- Type hints on new backend functions; mypy runs in `task check`.
- Ghost detection is a **heuristic**. User-facing wording is "appears unchanged", never "the model was wrong".

---

### Task 1: `analysis.py` — detect spans that changed nothing

**Files:**
- Create: `backend/analysis.py`
- Test: `backend/tests/test_analysis.py`

**Interfaces:**
- Consumes: nothing. Pure stdlib, no imports from `providers` or `store`.
- Produces:
  - `strip_marks(correction: str) -> tuple[str, list[dict[str, Any]]]` — text without tags, plus spans `{text, type, offset, end}` where offsets index the returned text.
  - `ghost_marks(original: str, correction: str) -> list[dict[str, Any]]` — spans `{text, type, offset}`.
  - `is_no_op(original: str, correction: str) -> bool`
  - `word_diff(original: str, correction: str) -> list[dict[str, str]]` — segments `{op, before, after}`, `op` one of `equal|replace|insert|delete`.
  - `analyse(original: str, correction: str) -> dict[str, Any]` — `{"no_op": bool, "ghost_marks": [...], "diff": [...]}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_analysis.py`. The three constants are real results copied verbatim from the dashboard on 2026-08-10 — do not paraphrase them, they are the reason this module exists.

```python
from analysis import analyse, ghost_marks, is_no_op, strip_marks, word_diff

# Each fixture reproduces a real failure, with the wording replaced by
# synthetic text. Only the subject matter is invented: every marked span,
# every misspelling and every corrected word sits where it did in the
# original, so the word alignment these tests pin down is unchanged.

# The model claimed "have decided" needed the past participle. It already
# was one: nothing in the correction differs from the original.
ID13_PROMPT = "Remind me what we have decided about the demo catalogue. I still see Northwind and Kestrel with autosuggestions"
ID13_CORRECTION = 'Remind me what we have <mark data-type="grammar">decided</mark> about the demo catalogue. I still see Northwind and Kestrel with autosuggestions'

# Two genuine fixes plus one invented: the article was said to be missing
# in "both occurrences", but the first occurrence already had it.
ID14_PROMPT = "Look at the entry above (the one about the demo catalogue). It looks as if it is a false positive. I asked another model and it confirmed that but also suggested that in this situation they'd rather use past simple instead of present perfect. So why falce positive and how can I get suggestions like that?"
ID14_CORRECTION = 'Look at the entry above (the one about the demo catalogue). It looks as if it is <mark data-type="grammar">a</mark> false positive. I asked another model and it confirmed that but also suggested that in this situation they\'d rather use past simple instead of present perfect. So why <mark data-type="grammar">a</mark> <mark data-type="spelling">false</mark> positive and how can I get suggestions like that?'

# Four genuine fixes plus one invented "the". This is the case that
# distinguishes per-span alignment from a blanket "correction == original"
# rule: the correction really does differ, in four other places.
ID32_PROMPT = "Write down a note to discuss: I want to mark (one by one) items as approved, which means they need to get a mark in the left panel (check/uncheck) so I can see which are unapproved + a zero-size (if absent) adjutment as I did before. This should be possible only if all entries in item are approved.\n+ Uncheck marks in all items in one button (could ebe at the very bottom)"
ID32_CORRECTION = 'Write down a note to discuss: I want to mark (one by one) items as approved, which means they need to get a mark in the left panel (check/uncheck) so I can see which are unapproved + a zero-size (if absent) <mark data-type="spelling">adjustment</mark> as I did before. This should be possible only if all entries in <mark data-type="grammar">an item</mark> are approved.\n+ Uncheck marks in all items <mark data-type="word-choice">with</mark> one button (could <mark data-type="spelling">be</mark> at <mark data-type="grammar">the</mark> very bottom)'

# Every mark is a real change. The detector must stay silent here.
CLEAN_PROMPT = "3. We need to take into account the seasonal variation and look to the last 3 years\nLooking at the rest right away"
CLEAN_CORRECTION = '3. We need to take into account the seasonal variation and look <mark data-type="grammar">at</mark> the last 3 years\nLooking at the rest right away'


def test_whole_correction_changed_nothing():
    assert is_no_op(ID13_PROMPT, ID13_CORRECTION) is True
    ghosts = ghost_marks(ID13_PROMPT, ID13_CORRECTION)
    assert [g["text"] for g in ghosts] == ["decided"]
    assert ghosts[0]["type"] == "grammar"


def test_one_ghost_among_two_real_fixes():
    ghosts = ghost_marks(ID14_PROMPT, ID14_CORRECTION)
    assert [g["text"] for g in ghosts] == ["a"]
    # The *first* "a" is the invented one; the second really was inserted.
    stripped, _ = strip_marks(ID14_CORRECTION)
    assert stripped[: ghosts[0]["offset"]].endswith("as if it is ")


def test_one_ghost_among_four_real_fixes():
    # The case a blanket "nothing changed" rule would miss entirely.
    assert is_no_op(ID32_PROMPT, ID32_CORRECTION) is False
    ghosts = ghost_marks(ID32_PROMPT, ID32_CORRECTION)
    assert [g["text"] for g in ghosts] == ["the"]


def test_genuine_correction_reports_no_ghosts():
    # More important than any positive case: a detector that cries wolf on
    # good results is worse than no detector.
    assert ghost_marks(CLEAN_PROMPT, CLEAN_CORRECTION) == []
    assert is_no_op(CLEAN_PROMPT, CLEAN_CORRECTION) is False


def test_multi_word_mark_unchanged_is_a_ghost():
    assert [g["text"] for g in ghost_marks("a b c d", 'a <mark data-type="grammar">b c</mark> d')] == ["b c"]


def test_multi_word_mark_changed_is_not():
    assert ghost_marks("a b c d", 'a <mark data-type="grammar">B C</mark> d') == []


def test_adjacent_marks_judged_separately():
    ghosts = ghost_marks("cant go", '<mark data-type="grammar">can\'t</mark> <mark data-type="style">go</mark>')
    assert [g["text"] for g in ghosts] == ["go"]


def test_punctuation_inside_a_mark_counts_as_a_change():
    assert ghost_marks("hello world", '<mark data-type="grammar">hello,</mark> world') == []


def test_empty_correction_is_not_a_no_op():
    # No correction means the model reported nothing to fix, which is not the
    # same as claiming a fix that does nothing.
    assert analyse("some text", "") == {"no_op": False, "ghost_marks": [], "diff": []}


def test_correction_without_marks():
    assert ghost_marks("some text", "some other text") == []


def test_strip_marks_offsets_point_into_the_stripped_text():
    stripped, spans = strip_marks('a <mark data-type="spelling">B</mark> c')
    assert stripped == "a B c"
    assert spans[0]["offset"] == 2
    assert spans[0]["end"] == 3
    assert spans[0]["type"] == "spelling"
    assert stripped[spans[0]["offset"] : spans[0]["end"]] == "B"


def test_word_diff_reports_a_single_equal_run_when_nothing_changed():
    diff = word_diff(ID13_PROMPT, ID13_CORRECTION)
    assert [segment["op"] for segment in diff] == ["equal"]


def test_word_diff_names_each_real_change():
    diff = word_diff(ID32_PROMPT, ID32_CORRECTION)
    changes = [(s["op"], s["before"], s["after"]) for s in diff if s["op"] != "equal"]
    assert changes == [
        ("replace", "adjutment", "adjustment"),
        ("insert", "", "an"),
        ("replace", "in", "with"),
        ("replace", "ebe", "be"),
    ]
    # "the" is marked in the correction but appears in no change segment.
    assert all("the" != s["after"] for s in changes)


def test_analyse_bundles_the_three_reports():
    result = analyse(ID32_PROMPT, ID32_CORRECTION)
    assert result["no_op"] is False
    assert [g["text"] for g in result["ghost_marks"]] == ["the"]
    assert any(s["op"] == "replace" for s in result["diff"])
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `cd backend && uv run pytest tests/test_analysis.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'analysis'`.

- [ ] **Step 3: Write the implementation**

Create `backend/analysis.py`:

```python
"""What a correction actually changed, independent of any provider.

Pure functions over (original, correction). They report where the model marked a
span it did not in fact change — a strong hint that the finding behind it was
invented rather than merely worded oddly.

Nothing here alters a verdict. Word alignment is a heuristic: on a heavily
rewritten multi-paragraph correction it can align badly and call a real change a
ghost, so these findings are recorded for a human to read, not acted on.
"""

import difflib
import re
from typing import Any

_MARKED = re.compile(r"<mark[^>]*>(.*?)</mark>", re.S)
_SPLIT = re.compile(r"(<mark[^>]*>.*?</mark>)", re.S)
_DATA_TYPE = re.compile(r'data-type="([^"]*)"')
_WORD = re.compile(r"\S+")


def strip_marks(correction: str) -> tuple[str, list[dict[str, Any]]]:
    """The correction without its tags, plus every marked span located in it.

    Offsets index the returned text, so a caller can find a span again without
    parsing the markup a second time.
    """
    out: list[str] = []
    spans: list[dict[str, Any]] = []
    pos = 0
    for part in _SPLIT.split(correction):
        if not part:
            continue
        marked = _MARKED.fullmatch(part)
        if marked:
            body = marked.group(1)
            found = _DATA_TYPE.search(part)
            spans.append(
                {
                    "text": body,
                    "type": found.group(1) if found else "",
                    "offset": pos,
                    "end": pos + len(body),
                }
            )
            out.append(body)
            pos += len(body)
        else:
            out.append(part)
            pos += len(part)
    return "".join(out), spans


def _words(text: str) -> list[str]:
    return [m.group() for m in _WORD.finditer(text)]


def _opcodes(original: str, stripped: str) -> list[tuple[str, int, int, int, int]]:
    matcher = difflib.SequenceMatcher(
        a=_words(original), b=_words(stripped), autojunk=False
    )
    return matcher.get_opcodes()


def ghost_marks(original: str, correction: str) -> list[dict[str, Any]]:
    """Marked spans covering only words that are unchanged from the original."""
    stripped, spans = strip_marks(correction)
    changed: set[int] = set()
    for tag, _i1, _i2, j1, j2 in _opcodes(original, stripped):
        if tag in ("replace", "insert"):
            changed.update(range(j1, j2))

    positions = [(m.start(), m.end()) for m in _WORD.finditer(stripped)]
    ghosts: list[dict[str, Any]] = []
    for span in spans:
        covered = [
            i
            for i, (start, end) in enumerate(positions)
            if start < span["end"] and end > span["offset"]
        ]
        if covered and not any(i in changed for i in covered):
            ghosts.append(
                {"text": span["text"], "type": span["type"], "offset": span["offset"]}
            )
    return ghosts


def is_no_op(original: str, correction: str) -> bool:
    """True when the correction says exactly what the original already said."""
    stripped, _ = strip_marks(correction)
    return stripped.strip() == original.strip()


def word_diff(original: str, correction: str) -> list[dict[str, str]]:
    """The correction against the original, as flat segments for a renderer.

    Emitted server-side so the browser never needs its own diff: the algorithm
    is already here, and a second implementation would be a second thing to keep
    correct.
    """
    stripped, _ = strip_marks(correction)
    before, after = _words(original), _words(stripped)
    return [
        {
            "op": tag,
            "before": " ".join(before[i1:i2]),
            "after": " ".join(after[j1:j2]),
        }
        for tag, i1, i2, j1, j2 in _opcodes(original, stripped)
    ]


def analyse(original: str, correction: str) -> dict[str, Any]:
    """Everything the debug panel reports about one correction."""
    if not correction:
        return {"no_op": False, "ghost_marks": [], "diff": []}
    return {
        "no_op": is_no_op(original, correction),
        "ghost_marks": ghost_marks(original, correction),
        "diff": word_diff(original, correction),
    }
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd backend && uv run pytest tests/test_analysis.py -v`
Expected: 13 passed.

- [ ] **Step 5: Run the whole check suite**

Run: `cd backend && uv run task check`
Expected: ruff clean, mypy clean, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/analysis.py backend/tests/test_analysis.py
git commit -m "feat: detect marked spans that changed nothing

Three results in one day claimed a function word was missing when it was
already there, then marked the unchanged word. Alignment against the
original finds exactly that, per span rather than per result — id 32 had
four genuine fixes beside the invented one."
```

---

### Task 2: Capture a debug record on every check

**Files:**
- Modify: `backend/providers/__init__.py`
- Modify: `backend/providers/openai.py`
- Modify: `backend/store.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_providers.py`, `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `analysis.analyse(original, correction) -> dict` from Task 1.
- Produces:
  - `providers.SYSTEM_PROMPT_HASH: str` — first 8 hex chars of the SHA-256 of `SYSTEM_PROMPT`.
  - `GrammarResult.raw: dict[str, Any]`, `GrammarResult.dropped_issues: list[dict[str, str]]`, `GrammarResult.usage: dict[str, int]`.
  - `CheckResult.debug: dict[str, Any] | None`.
  - `CheckResult.to_dict()` gains `"has_ghost_marks": bool`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_providers.py`:

```python
def test_build_result_keeps_the_raw_response():
    data = {"issues": [{"type": "grammar", "note": "n"}], "correction": "c"}
    assert build_result(data).raw == data


def test_build_result_records_what_it_dropped():
    # build_result silently filters types outside ISSUE_TYPES. Silently is the
    # problem: a model emitting a new category vanished without trace.
    data = {
        "issues": [
            {"type": "grammar", "note": "kept"},
            {"type": "clarity", "note": "dropped"},
        ],
        "correction": "",
    }
    result = build_result(data)
    assert [i["note"] for i in result.issues] == ["kept"]
    assert result.dropped_issues == [{"type": "clarity", "note": "dropped"}]


def test_system_prompt_hash_is_stable_and_short():
    from providers import SYSTEM_PROMPT_HASH

    assert len(SYSTEM_PROMPT_HASH) == 8
    assert SYSTEM_PROMPT_HASH == SYSTEM_PROMPT_HASH
```

Append to `backend/tests/test_store.py`:

```python
def test_debug_is_not_broadcast():
    # The panel is fetched on demand; shipping it to every client on every
    # check would multiply the payload for something read twice a day.
    result = CheckResult(
        username="a",
        prompt="p",
        has_issues=False,
        explanation="",
        debug={"raw": {"issues": []}},
    )
    assert "debug" not in result.to_dict()
    assert result.debug == {"raw": {"issues": []}}


def test_has_ghost_marks_is_broadcast():
    # The entry marker must be decidable from the broadcast payload, or
    # enabling debug would fire one request per visible entry.
    flagged = CheckResult(
        username="a",
        prompt="p",
        has_issues=True,
        explanation="",
        debug={"analysis": {"ghost_marks": [{"text": "the"}]}},
    )
    assert flagged.to_dict()["has_ghost_marks"] is True


def test_has_ghost_marks_defaults_false_without_debug():
    plain = CheckResult(username="a", prompt="p", has_issues=False, explanation="")
    assert plain.to_dict()["has_ghost_marks"] is False
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_providers.py tests/test_store.py -v`
Expected: failures — `GrammarResult` has no `raw`, `ImportError` for `SYSTEM_PROMPT_HASH`, `CheckResult` has no `debug`.

- [ ] **Step 3: Extend `GrammarResult` and `build_result`**

In `backend/providers/__init__.py`, add `import hashlib` at the top, and extend the dataclass:

```python
@dataclass
class GrammarResult:
    has_issues: bool
    explanation: str
    types: list[str] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    correction: str = ""
    # Kept for the debug panel, never for display: the response exactly as the
    # provider returned it, and whatever normalisation removed from it.
    raw: dict[str, Any] = field(default_factory=dict)
    dropped_issues: list[dict[str, str]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
```

Replace the body of `build_result`:

```python
def build_result(data: dict[str, Any]) -> GrammarResult:
    """Turn a provider's schema-shaped response into a GrammarResult.

    Shared by all three providers: they differ in how they obtain the dict, not
    in what it means. A style note is a remark, not a fault, so it never sets
    has_issues on its own.
    """
    reported = data.get("issues", [])
    issues = [
        {"type": str(i["type"]), "note": str(i.get("note", ""))}
        for i in reported
        if i.get("type") in ISSUE_TYPES
    ]
    dropped = [
        {"type": str(i.get("type", "")), "note": str(i.get("note", ""))}
        for i in reported
        if i.get("type") not in ISSUE_TYPES
    ]
    types = list(dict.fromkeys(i["type"] for i in issues))
    return GrammarResult(
        has_issues=any(i["type"] != "style" for i in issues),
        explanation="",
        types=types,
        issues=issues,
        correction=str(data.get("correction", "")),
        raw=data,
        dropped_issues=dropped,
    )
```

Add below the `SYSTEM_PROMPT` definition:

```python
# Stored with every result so two results can be told apart by the prompt that
# produced them. The text itself is 2.3 KB and identical across a run, so it is
# served once from its own endpoint rather than copied 1000 times.
SYSTEM_PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8]
```

- [ ] **Step 4: Capture token usage in the OpenAI provider**

In `backend/providers/openai.py`, replace the final `return`:

```python
        result = build_result(parse_provider_json(content))
        # Only OpenAI reports usage in this shape; the other two SDKs differ, so
        # the field stays optional rather than complicating all three.
        if response.usage is not None:
            result.usage = {
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
            }
        return result
```

- [ ] **Step 5: Add `debug` to `CheckResult`**

In `backend/store.py`, extend the dataclass and `to_dict`:

```python
@dataclass
class CheckResult:
    username: str
    prompt: str
    has_issues: bool
    explanation: str
    status: str = ""
    timestamp: str = ""
    id: int = 0
    project: str = ""
    agent: str = ""
    run_id: str = ""
    types: list[str] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    correction: str = ""
    # Everything captured about how this result was produced. Deliberately kept
    # out of to_dict(): it is fetched per result when a panel is opened.
    debug: dict[str, Any] | None = None

    def has_ghost_marks(self) -> bool:
        """Whether analysis found a marked span that changed nothing."""
        if not self.debug:
            return False
        analysis = self.debug.get("analysis") or {}
        return bool(analysis.get("ghost_marks"))
```

Add `from typing import Any` to the imports, and add one line to `to_dict`, next to `"correction"`:

```python
            "has_ghost_marks": self.has_ghost_marks(),
```

- [ ] **Step 6: Build the debug record in `_run_check`**

In `backend/main.py`, add `import time` and the imports `from analysis import analyse` and `from providers import SYSTEM_PROMPT_HASH, create_provider`.

Store the settings in `lifespan` so the endpoint can name the provider — add this line just before `yield`:

```python
    app.state.settings = settings
```

Pass them through in the `check` endpoint, replacing the `_run_check(...)` call:

```python
    task = asyncio.create_task(
        _run_check(
            request.app.state.store,
            request.app.state.provider,
            username,
            body.prompt,
            body.project,
            body.agent,
            provider_name=request.app.state.settings.provider,
            model=request.app.state.settings.model,
        )
    )
```

Replace `_run_check` entirely:

```python
async def _run_check(
    store: ResultStore,
    provider,
    username: str,
    prompt: str,
    project: str = "",
    agent: str = "",
    *,
    provider_name: str = "",
    model: str = "",
):
    request_meta = {
        "provider": provider_name,
        "model": model,
        "system_prompt_hash": SYSTEM_PROMPT_HASH,
    }
    started = time.perf_counter()
    try:
        result = await provider.check_grammar(prompt)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        check_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=result.has_issues,
            explanation=result.explanation,
            types=result.types,
            issues=result.issues,
            correction=result.correction,
            project=project,
            agent=agent,
            debug={
                "request": request_meta,
                "raw": result.raw,
                "derived": {"dropped_issues": result.dropped_issues},
                "timing": {"latency_ms": elapsed_ms, "usage": result.usage},
                "analysis": analyse(prompt, result.correction),
            },
        )
        await store.add_and_broadcast(check_result)
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        error_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=False,
            explanation=f"Grammar check failed: {e}",
            status="error",
            project=project,
            agent=agent,
            # A failure previously left only the formatted message. The type is
            # what tells a timeout apart from a schema rejection.
            debug={
                "request": request_meta,
                "error": {"type": type(e).__name__, "message": str(e)},
                "timing": {"latency_ms": elapsed_ms},
            },
        )
        await store.add_and_broadcast(error_result)
```

- [ ] **Step 7: Run the tests and watch them pass**

Run: `cd backend && uv run task check`
Expected: ruff clean, mypy clean, all tests pass — the pre-existing ones included, since no verdict field changed.

- [ ] **Step 8: Commit**

```bash
git add backend/providers/__init__.py backend/providers/openai.py backend/store.py backend/main.py backend/tests/test_providers.py backend/tests/test_store.py
git commit -m "feat: record how each check was produced

Every check now keeps the raw response, what normalisation dropped, the
timing and the span analysis. Kept off the broadcast payload apart from a
has_ghost_marks flag, which the entry marker needs to be decidable without
a request per entry."
```

---

### Task 3: Serve the debug record

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_debug.py` (create)

**Interfaces:**
- Consumes: `CheckResult.debug` from Task 2, `providers.SYSTEM_PROMPT_HASH`.
- Produces: `GET /api/results/{result_id}/debug` and `GET /api/debug/system-prompt`, both behind `require_username`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_debug.py`:

```python
from unittest.mock import patch

import pytest

from store import CheckResult


@pytest.mark.asyncio
async def test_debug_requires_auth(client, store):
    store.add(CheckResult(username="a", prompt="p", has_issues=False, explanation=""))
    resp = await client.get("/api/results/1/debug")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_debug_returns_the_captured_record(client, auth, store):
    store.add(
        CheckResult(
            username="a",
            prompt="p",
            has_issues=False,
            explanation="",
            debug={"request": {"model": "gpt-5.6-terra"}},
        )
    )
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results/1/debug", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json()["request"]["model"] == "gpt-5.6-terra"


@pytest.mark.asyncio
async def test_debug_404_for_unknown_id(client, auth, store):
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results/999/debug", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_debug_empty_object_when_nothing_was_captured(client, auth, store):
    store.add(CheckResult(username="a", prompt="p", has_issues=False, explanation=""))
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results/1/debug", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_system_prompt_is_served_whole(client, auth):
    from providers import SYSTEM_PROMPT, SYSTEM_PROMPT_HASH

    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/debug/system-prompt", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"hash": SYSTEM_PROMPT_HASH, "text": SYSTEM_PROMPT}


@pytest.mark.asyncio
async def test_system_prompt_requires_auth(client):
    resp = await client.get("/api/debug/system-prompt")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && uv run pytest tests/test_debug.py -v`
Expected: 404s where 200s are asserted — the routes do not exist yet.

- [ ] **Step 3: Add the endpoints**

In `backend/main.py`, add `SYSTEM_PROMPT` to the `providers` import, and add both routes after the existing `results` endpoint:

```python
@app.get("/api/results/{result_id}/debug")
async def result_debug(
    result_id: int,
    request: Request,
    _username: str = Depends(require_username),
):
    """Everything captured about one check.

    Ids restart with every backend run, so this resolves against the running
    process's store — the only one that exists.
    """
    for result in request.app.state.store.results:
        if result.id == result_id:
            return result.debug or {}
    raise HTTPException(status_code=404, detail="not found")


@app.get("/api/debug/system-prompt")
async def system_prompt(_username: str = Depends(require_username)):
    """The prompt behind every result, stored per result only as a hash."""
    return {"hash": SYSTEM_PROMPT_HASH, "text": SYSTEM_PROMPT}
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `cd backend && uv run task check`
Expected: all pass, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_debug.py
git commit -m "feat: serve a result's debug record on demand"
```

---

### Task 4: The dashboard debug panel

**Files:**
- Modify: `frontend/static/index.html`
- Modify: `frontend/static/app.js`
- Modify: `frontend/static/style.css`

**Interfaces:**
- Consumes: `GET /api/results/{id}/debug` from Task 3; `has_ghost_marks` on every broadcast result from Task 2.
- Produces: nothing consumed by later tasks. This is the last one.

There is no frontend test suite. Verification is `node --check` plus the manual browser pass in Step 6 — do not skip it, and do not claim the panel works without having opened one.

- [ ] **Step 1: Add the toggle button**

In `frontend/static/index.html`, inside `.header-actions`, before the theme toggle:

```html
            <button id="debug-toggle" type="button" title="Debug view" aria-label="Debug view">⚙</button>
```

- [ ] **Step 2: Wire the toggle in `app.js`**

Add after the theme block (which ends with `paintToggle();`):

```javascript
// --- Debug view -------------------------------------------------------------
// A body class rather than a re-render: entries already in the feed pick the
// change up through CSS, so toggling never rebuilds the list.
const debugToggle = document.getElementById("debug-toggle");

function debugEnabled() {
    try {
        return localStorage.getItem("hoshi-debug") === "on";
    } catch (e) {
        return false;
    }
}

function paintDebugToggle() {
    const on = debugEnabled();
    document.body.classList.toggle("debug-on", on);
    debugToggle.classList.toggle("active", on);
    debugToggle.title = on ? "Hide debug view" : "Debug view";
    debugToggle.setAttribute("aria-label", debugToggle.title);
}

debugToggle.addEventListener("click", () => {
    try {
        localStorage.setItem("hoshi-debug", debugEnabled() ? "off" : "on");
    } catch (e) { /* private mode: the choice just does not survive a reload */ }
    paintDebugToggle();
});

paintDebugToggle();
```

- [ ] **Step 3: Render the link and marker in each entry**

In `renderResult`, add above the `entry.innerHTML` assignment:

```javascript
    // Rendered always, revealed by CSS only under the debug toggle — so the
    // feed never has to be rebuilt when the toggle flips.
    const ghostFlag = data.has_ghost_marks
        ? `<span class="ghost-flag" title="A marked span appears unchanged">!</span>`
        : "";
    const debugLink = `<button type="button" class="debug-link" data-id="${data.id}">debug</button>`;
```

Add both to the header template, after `${typeTags}`:

```javascript
            ${ghostFlag}
            ${debugLink}
```

- [ ] **Step 4: Fetch and render the panel**

Add at the end of `app.js`:

```javascript
// One listener on the feed rather than one per entry: entries are prepended
// continuously, and a delegated handler covers the ones not yet created.
feed.addEventListener("click", async (event) => {
    const link = event.target.closest(".debug-link");
    if (!link) {
        return;
    }
    const entry = link.closest(".entry");
    const existing = entry.querySelector(".debug-panel");
    if (existing) {
        existing.remove();
        return;
    }

    const panel = document.createElement("div");
    panel.className = "debug-panel";
    panel.textContent = "loading…";
    entry.appendChild(panel);

    try {
        const resp = await fetch(`/api/results/${link.dataset.id}/debug`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) {
            panel.textContent = `debug unavailable (${resp.status})`;
            return;
        }
        panel.innerHTML = renderDebug(await resp.json());
    } catch (e) {
        panel.textContent = `debug unavailable (${e.message})`;
    }
});

function renderDebug(debug) {
    const analysis = debug.analysis || {};
    const ghosts = analysis.ghost_marks || [];

    // Worded as an observation, not a verdict: word alignment is a heuristic,
    // and nothing in the pipeline acts on it.
    let verdict = "";
    if (analysis.no_op) {
        verdict = "the correction is identical to the original — nothing changed";
    } else if (ghosts.length) {
        const words = ghosts.map((g) => `“${escapeHtml(g.text)}”`).join(", ");
        verdict = `${ghosts.length} marked span${ghosts.length > 1 ? "s appear" : " appears"} unchanged: ${words}`;
    }
    const analysisHtml = verdict
        ? `<div class="debug-verdict">${verdict}</div>`
        : `<div class="debug-ok">every marked span matches a real change</div>`;

    const diffHtml = (analysis.diff || [])
        .map((seg) => {
            if (seg.op === "equal") {
                return `<span class="d-equal">${escapeHtml(seg.before)}</span>`;
            }
            const before = seg.before
                ? `<del>${escapeHtml(seg.before)}</del>`
                : "";
            const after = seg.after ? `<ins>${escapeHtml(seg.after)}</ins>` : "";
            return `${before}${after}`;
        })
        .join(" ");

    const request = debug.request || {};
    const timing = debug.timing || {};
    const usage = timing.usage || {};
    const meta = [
        request.provider,
        request.model,
        request.system_prompt_hash ? `prompt ${request.system_prompt_hash}` : "",
        timing.latency_ms !== undefined ? `${(timing.latency_ms / 1000).toFixed(1)}s` : "",
        usage.input !== undefined ? `${usage.input} in / ${usage.output} out` : "",
    ]
        .filter(Boolean)
        .map(escapeHtml)
        .join(" · ");

    const dropped = (debug.derived || {}).dropped_issues || [];
    const droppedHtml = dropped.length
        ? `<div class="debug-dropped">${dropped.length} issue${dropped.length > 1 ? "s" : ""} dropped as an unknown type: ${dropped
              .map((i) => escapeHtml(i.type))
              .join(", ")}</div>`
        : "";

    const errorHtml = debug.error
        ? `<div class="debug-verdict">${escapeHtml(debug.error.type)}: ${escapeHtml(debug.error.message)}</div>`
        : "";

    return `
        ${errorHtml}
        ${debug.error ? "" : analysisHtml}
        ${diffHtml ? `<div class="debug-diff">${diffHtml}</div>` : ""}
        ${droppedHtml}
        <div class="debug-meta">${meta}</div>
        <pre class="debug-raw">${escapeHtml(JSON.stringify(debug.raw || {}, null, 2))}</pre>
    `;
}
```

- [ ] **Step 5: Style it**

Append to `frontend/static/style.css`. Every colour is a token — a literal hex here would be a bug in one of the two themes:

```css
/* The debug view. Hidden entirely unless the toggle is on, so the normal feed
   is untouched by any of this. */
#debug-toggle {
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--fg-muted);
    cursor: pointer;
    font-size: 0.9rem;
    line-height: 1;
    padding: 0.3rem 0.5rem;
}
#debug-toggle:hover { color: var(--fg); border-color: var(--fg-muted); }
#debug-toggle.active { color: var(--c-word-choice); border-color: var(--c-word-choice); }

.debug-link, .ghost-flag { display: none; }
body.debug-on .debug-link {
    display: inline-block;
    background: none;
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--fg-muted);
    cursor: pointer;
    font-family: inherit;
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
}
body.debug-on .debug-link:hover { color: var(--fg); }
body.debug-on .ghost-flag {
    display: inline-block;
    background: color-mix(in srgb, var(--c-grammar) var(--tint), transparent);
    color: var(--c-grammar);
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.15rem 0.4rem;
}

.debug-panel {
    margin-top: 0.75rem;
    padding: 0.6rem;
    background: var(--inset);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.8rem;
}
.debug-verdict { color: var(--c-grammar); font-weight: 600; margin-bottom: 0.5rem; }
.debug-ok { color: var(--fg-muted); margin-bottom: 0.5rem; }
.debug-dropped { color: var(--c-word-choice); margin: 0.5rem 0; }
.debug-diff { line-height: 1.6; margin-bottom: 0.5rem; }
.debug-diff .d-equal { color: var(--fg-muted); }
.debug-diff del {
    background: color-mix(in srgb, var(--c-grammar) var(--tint), transparent);
    color: var(--c-grammar);
    text-decoration: line-through;
    padding: 0.05rem 0.2rem;
    border-radius: 3px;
}
.debug-diff ins {
    background: color-mix(in srgb, var(--c-neutral) var(--tint), transparent);
    color: var(--c-neutral);
    text-decoration: none;
    padding: 0.05rem 0.2rem;
    border-radius: 3px;
    margin-left: 0.2rem;
}
.debug-meta {
    color: var(--fg-muted);
    font-family: monospace;
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
}
.debug-raw {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.75rem;
    max-height: 18em;
    overflow: auto;
    padding: 0.5rem;
    white-space: pre;
}
```

- [ ] **Step 6: Verify in the browser**

```bash
node --check frontend/static/app.js
docker compose up -d --build
```

Rebuilding clears the store, so seed a result that is known to produce a ghost — this is the `ID13` case, and the model reproduces it reliably:

```bash
. ~/.hoshi/config
curl -s -X POST "$HOSHI_SERVER_URL/api/check" \
  -H "Authorization: Bearer $HOSHI_TOKEN" -H 'Content-Type: application/json' \
  -d '{"prompt":"Remind me what we have decided about the demo catalogue. I still see Northwind and Kestrel with autosuggestions","project":"sample-project","agent":"dashboard"}'
```

Then at `http://localhost:8080`, confirm each of:

1. With debug **off**, the feed looks exactly as before — no `debug` button, no `!` marker.
2. Toggling debug **on** reveals a `debug` button on every entry, and the toggle itself turns orange.
3. Clicking `debug` expands a panel; clicking again collapses it.
4. If the seeded result reproduced the false positive, the panel's first line reads *"the correction is identical to the original"* and the entry carries a red `!`. If the model got it right this time, the panel reads *"every marked span matches a real change"* — also correct, and worth confirming, since that is the common case.
5. The request line shows provider, model, prompt hash, latency and token counts.
6. The raw JSON matches what the entry displays.
7. Reload: the toggle state survives, and the panel state does not (panels start collapsed).
8. Switch themes with debug open — no unreadable text in either.

- [ ] **Step 7: Commit**

```bash
git add frontend/static/index.html frontend/static/app.js frontend/static/style.css
git commit -m "feat: add the dashboard debug panel

Off by default and invisible when off. Under the toggle, each entry gains a
panel with the span analysis first, then the word diff, the request line and
the raw response — ordered by what gets read first."
```

---

### Task 5: Document it

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above. Produces nothing.

- [ ] **Step 1: Add the convention to `CLAUDE.md`**

Under "How a check is shaped", after the `<mark data-type=...>` bullet:

```markdown
- Every check stores a `debug` record: the raw response, what `build_result`
  dropped, timing, and an analysis of which marked spans changed nothing.
  `analysis.py` is pure and knows no provider. It **observes only** — no verdict
  depends on it, because word alignment is a heuristic and suppressing a finding
  on a bad alignment would throw away a real correction
- `debug` is deliberately absent from `to_dict()`, so it never rides the
  WebSocket; only the derived `has_ghost_marks` bool does. Fetch a record from
  `/api/results/{id}/debug`
```

- [ ] **Step 2: Add a README section**

After the "Hook configuration" section:

```markdown
### Debug view

The ⚙ toggle in the header reveals a `debug` button on every result. The panel
shows whether any highlighted span actually changed anything, a word-level diff
against your original, the model and latency behind the check, and the raw
response.

It exists because the model occasionally reports a mistake that is not there —
claiming a word is missing when it is already present, then "correcting" the
text to what it already said. A span that changed nothing is the tell. Nothing
is suppressed on that basis: the analysis is shown, and the judgement is yours.
```

- [ ] **Step 3: Verify and commit**

Run: `cd backend && uv run task check`

```bash
git add CLAUDE.md README.md
git commit -m "docs: describe the debug view"
```

---

## Self-review

**Spec coverage.** Capture (Task 2), ghost analysis and word diff (Task 1), both endpoints (Task 3), toggle, panel ordering and entry marker (Task 4), documentation (Task 5). Every test named in the spec appears: the three real cases and the cry-wolf inverse in Task 1; awkward marks in Task 1; endpoint auth, 404 and `to_dict` exclusion in Tasks 2–3; the error path in Task 2.

**Two spec refinements made while planning**, both already written back into the spec:
- `to_dict()` gains a derived `has_ghost_marks` bool. The spec said `debug` is excluded and the payload unchanged, but the entry marker cannot be decided without it, and fetching per entry to find out would be worse.
- The word diff is computed server-side and shipped in `analysis.diff`. The spec did not say where it ran; Python already has the opcodes, so the browser renders rather than re-implements.

**Interfaces.** `analyse` returns `{no_op, ghost_marks, diff}` in Task 1 and is consumed under exactly those keys in Tasks 2 and 4. `has_ghost_marks` is a method on `CheckResult` (Task 2) and a payload key read by `renderResult` (Task 4). `SYSTEM_PROMPT_HASH` is defined in Task 2 and imported in Task 3.

**Expected values are measured, not guessed.** Every assertion in Task 1 — the ghost texts, the four diff segments for `id=32`, the offsets in `strip_marks` — was produced by running this exact implementation against the real corpus before the plan was written.
