# Named Checkers and Second Opinions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `PROVIDER`/`MODEL` pair with a named list of checkers in `checkers.json`, and let the dashboard attach a second opinion from any non-default checker to an existing result.

**Architecture:** A new `checkers.py` loads and validates the list at startup and eagerly constructs one `GrammarProvider` per entry (a config error kills the container). The hook path always uses the single default checker. A new endpoint runs a named checker against a stored result's prompt and attaches the outcome as an opinion; the result is re-broadcast and the dashboard replaces the entry in place. Ollama needs no new provider: `OpenAIProvider` gains a `base_url`.

**Tech Stack:** Python 3.12, FastAPI, pydantic, pytest (+pytest_asyncio strict mode, SDK constructors mocked), vanilla JS frontend.

**Spec:** `docs/superpowers/specs/2026-08-15-checkers-config-design.md`

## Global Constraints

- Checker `name` is a slug: `^[a-z0-9-]{1,32}$` — same alphabet as `agent`.
- Exactly one checker has `default: true`; zero or more than one is a **startup error**.
- Missing/unreadable `checkers.json` (including a directory, which compose creates when the host file is absent) → fall back to a single checker named `default` built from `PROVIDER`/`MODEL`. No existing setup breaks.
- Placeholder API key for a `base_url` checker with no key configured: exactly `"ollama"`.
- Endpoints: `GET /api/checkers`; `POST /api/results/{result_id}/checks` → 202, body `{"checker": "<name>"}`; 404 unknown result, 422 unknown checker or checker already attached (the result's own checker counts as attached).
- `debug` (including per-opinion debug under `debug["opinions"][<name>]`) never rides the WebSocket — only `to_dict()` output does.
- Frontend: no literal colours in JS or new CSS — tokens on `:root` only, defined for all three theme blocks. Never put an unvalidated string into a class name.
- Checks run from the **repo root**: `uv run task check`. Frontend syntax: `node --check frontend/static/app.js`.
- The hook (`hook/hook.sh`) is untouched.

---

### Task 1: Ollama structured-output spike (decision gate)

Verifies the spec's one open risk: that Ollama's OpenAI-compatible `/v1` honors strict `response_format: json_schema` for `GRAMMAR_SCHEMA`. No production code changes.

**Files:**
- Create: `docs/superpowers/plans/2026-08-15-ollama-spike-notes.md` (findings; committed)

**Interfaces:**
- Produces: a go/no-go on "no fourth provider". **If strict json_schema is rejected or silently ignored, STOP the plan and report BLOCKED** — Tasks 2–9 assume it works; the fallback (a thin `OllamaProvider` on Ollama's native `format` field) needs a plan revision, not improvisation.

- [ ] **Step 1: Install and start Ollama, pull a small model**

```bash
brew install ollama
brew services start ollama
ollama pull qwen3:4b   # smallest tier that can plausibly follow the <mark> discipline
curl -s http://localhost:11434/api/version
```

- [ ] **Step 2: Run one check through the real provider path**

Write and run (from repo root, venv active) `/tmp/ollama_spike.py` — note it imports the *unmodified* provider, so `base_url` is not available yet; it constructs the SDK client the same way the provider will:

```python
import asyncio
import sys

sys.path.insert(0, "backend")

import openai
from providers import GRAMMAR_SCHEMA, SYSTEM_PROMPT, build_result, parse_provider_json

PROMPT = "i has been working on this all morning and the tests still dont pass"


async def main() -> None:
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
    result = build_result(parse_provider_json(resp.choices[0].message.content or ""))
    print("issues:", result.issues)
    print("correction:", result.correction)
    print("dropped:", result.dropped_issues)


asyncio.run(main())
```

Expected: no API error; `issues` is a list of `{type, note}` with types from the enum; `correction` contains `<mark data-type="...">` tags. Weak marks are acceptable (degrades ghost detection, which observes only); a 400 on `response_format`, or prose/malformed JSON, is a **FAIL → BLOCKED**.

- [ ] **Step 3: Verify the container can reach the host's Ollama**

```bash
docker compose -p hoshi exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5).read())"
```

Expected: the version JSON. (Docker Desktop forwards `host.docker.internal` to the host loopback.)

- [ ] **Step 4: Record findings and commit**

Write `docs/superpowers/plans/2026-08-15-ollama-spike-notes.md`: Ollama version, model, whether strict mode was honored, one sample `issues`/`correction` (from the fixed spike prompt above — never from a live result), latency. Commit:

```bash
git add docs/superpowers/plans/2026-08-15-ollama-spike-notes.md
git commit -m "docs: record the Ollama structured-output spike"
```

---

### Task 2: `base_url` on the OpenAI provider

**Files:**
- Modify: `backend/providers/openai.py` (the `__init__`)
- Modify: `backend/providers/__init__.py` (`create_provider`)
- Test: `backend/tests/test_providers.py`

**Interfaces:**
- Produces: `OpenAIProvider(api_key, model, base_url="")`; `create_provider(provider, model, *, ..., base_url="")`. `base_url` with a non-openai provider raises `ValueError`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_providers.py`, matching its existing `patch("providers.openai.openai.AsyncOpenAI")` style):

```python
def test_openai_provider_passes_base_url_and_placeholder_key():
    with patch("providers.openai.openai.AsyncOpenAI") as MockClient:
        from providers.openai import OpenAIProvider

        OpenAIProvider(api_key="", model="qwen3:4b", base_url="http://host.docker.internal:11434/v1")
        MockClient.assert_called_once_with(
            api_key="ollama", base_url="http://host.docker.internal:11434/v1"
        )


def test_openai_provider_without_base_url_keeps_its_key():
    with patch("providers.openai.openai.AsyncOpenAI") as MockClient:
        from providers.openai import OpenAIProvider

        OpenAIProvider(api_key="real-key", model="gpt-4o")
        MockClient.assert_called_once_with(api_key="real-key", base_url=None)


def test_create_provider_rejects_base_url_for_non_openai():
    with pytest.raises(ValueError, match="base_url"):
        create_provider("anthropic", "claude-x", anthropic_api_key="k", base_url="http://x")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest backend/tests/test_providers.py -q` (from repo root). Expected: FAIL — unexpected keyword `base_url`.

- [ ] **Step 3: Implement.** In `backend/providers/openai.py`:

```python
class OpenAIProvider:
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        # A local endpoint (Ollama) ignores the key, but the SDK refuses an
        # empty one; "ollama" is the conventional placeholder.
        if base_url and not api_key:
            api_key = "ollama"
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
```

In `create_provider`, add `base_url: str = ""` to the signature; pass it only in the `"openai"` case; before the `match`, guard:

```python
    if base_url and provider != "openai":
        raise ValueError(f"base_url is only supported for the openai provider, not {provider!r}")
```

- [ ] **Step 4: Run the suite** — `uv run task check`. Expected: PASS, lint and mypy clean.

- [ ] **Step 5: Commit** — `git add -A backend && git commit -m "feat: let the OpenAI provider target a compatible endpoint"`

---

### Task 3: The checkers loader

**Files:**
- Create: `backend/checkers.py`
- Modify: `backend/config.py` (one field)
- Test: `backend/tests/test_checkers.py`

**Interfaces:**
- Consumes: `create_provider` (Task 2 signature).
- Produces, for Tasks 5–6:

```python
@dataclass(frozen=True)
class CheckerConfig:
    name: str
    provider: str
    model: str
    default: bool = False
    base_url: str = ""

@dataclass
class Checkers:
    providers: dict[str, GrammarProvider]   # by name
    configs: dict[str, CheckerConfig]       # by name, insertion-ordered
    default: str                            # name of the default checker

def load_checkers(path, *, fallback_provider, fallback_model,
                  anthropic_api_key="", openai_api_key="", gemini_api_key="",
                  factory=create_provider) -> Checkers
```

- [ ] **Step 1: Add the setting.** In `backend/config.py`, after `tokens_file`: `checkers_file: str = "checkers.json"`.

- [ ] **Step 2: Write the failing tests** — `backend/tests/test_checkers.py`:

```python
import json

import pytest

from checkers import CheckerConfig, load_checkers


def fake_factory(calls):
    def factory(provider, model, **kwargs):
        calls.append((provider, model, kwargs))
        return object()

    return factory


def write(tmp_path, data):
    p = tmp_path / "checkers.json"
    p.write_text(json.dumps(data))
    return str(p)


VALID = {
    "checkers": [
        {"name": "terra", "provider": "openai", "model": "gpt-5.6-terra", "default": True},
        {"name": "qwen8", "provider": "openai", "model": "qwen3:8b",
         "base_url": "http://host.docker.internal:11434/v1"},
    ]
}


def test_loads_a_valid_file(tmp_path):
    calls = []
    cs = load_checkers(write(tmp_path, VALID), fallback_provider="openai",
                       fallback_model="x", openai_api_key="k", factory=fake_factory(calls))
    assert list(cs.configs) == ["terra", "qwen8"]
    assert cs.default == "terra"
    assert cs.configs["qwen8"].base_url == "http://host.docker.internal:11434/v1"
    assert [(p, m) for p, m, _ in calls] == [("openai", "gpt-5.6-terra"), ("openai", "qwen3:8b")]
    assert calls[0][2]["openai_api_key"] == "k"


def test_missing_file_falls_back_to_env_settings(tmp_path):
    cs = load_checkers(str(tmp_path / "absent.json"), fallback_provider="openai",
                       fallback_model="gpt-5.6-luna", factory=fake_factory([]))
    assert list(cs.configs) == ["default"]
    assert cs.default == "default"
    assert cs.configs["default"] == CheckerConfig(
        name="default", provider="openai", model="gpt-5.6-luna", default=True
    )


def test_a_directory_counts_as_absent(tmp_path):
    # docker compose creates a directory when the host file does not exist.
    (tmp_path / "checkers.json").mkdir()
    cs = load_checkers(str(tmp_path / "checkers.json"), fallback_provider="openai",
                       fallback_model="m", factory=fake_factory([]))
    assert list(cs.configs) == ["default"]


@pytest.mark.parametrize(
    "data,match",
    [
        ({"checkers": []}, "at least one"),
        ({"checkers": [{"name": "a", "provider": "openai", "model": "m"}]}, "default"),
        ({"checkers": [
            {"name": "a", "provider": "openai", "model": "m", "default": True},
            {"name": "b", "provider": "openai", "model": "m", "default": True},
        ]}, "default"),
        ({"checkers": [
            {"name": "dup", "provider": "openai", "model": "m", "default": True},
            {"name": "dup", "provider": "openai", "model": "m2"},
        ]}, "dup"),
        ({"checkers": [{"name": "Bad Name", "provider": "openai", "model": "m",
                        "default": True}]}, "slug"),
        ({"checkers": [{"name": "a", "provider": "openai", "default": True}]}, "model"),
    ],
)
def test_invalid_configs_die_loudly(tmp_path, data, match):
    with pytest.raises(ValueError, match=match):
        load_checkers(write(tmp_path, data), fallback_provider="openai",
                      fallback_model="m", factory=fake_factory([]))


def test_malformed_json_dies_loudly(tmp_path):
    p = tmp_path / "checkers.json"
    p.write_text("{nope")
    with pytest.raises(ValueError, match="checkers.json"):
        load_checkers(str(p), fallback_provider="openai", fallback_model="m",
                      factory=fake_factory([]))
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest backend/tests/test_checkers.py -q`. Expected: FAIL, no module `checkers`.

- [ ] **Step 4: Implement `backend/checkers.py`:**

```python
"""Load the named checker list, or synthesize one from the env settings.

Validation is deliberately fatal: this runs during startup, where a bad config
should kill the container, not surface later as a 500 with a stack trace.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from providers import GrammarProvider, create_provider

# Names become CSS hooks and API parameters, same as `agent` — same alphabet.
NAME_RE = re.compile(r"^[a-z0-9-]{1,32}$")


@dataclass(frozen=True)
class CheckerConfig:
    name: str
    provider: str
    model: str
    default: bool = False
    base_url: str = ""


@dataclass
class Checkers:
    providers: dict[str, GrammarProvider]
    configs: dict[str, CheckerConfig]
    default: str


def _parse(path: Path) -> list[CheckerConfig]:
    try:
        data: Any = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"checkers.json is not valid JSON: {e}") from e
    entries = data.get("checkers") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("checkers.json must define at least one entry under 'checkers'")

    configs: list[CheckerConfig] = []
    for entry in entries:
        name = str(entry.get("name", ""))
        if not NAME_RE.match(name):
            raise ValueError(f"checker name {name!r} is not a slug (^[a-z0-9-]{{1,32}}$)")
        if not entry.get("model"):
            raise ValueError(f"checker {name!r} has no model")
        configs.append(
            CheckerConfig(
                name=name,
                provider=str(entry.get("provider", "")),
                model=str(entry["model"]),
                default=bool(entry.get("default", False)),
                base_url=str(entry.get("base_url", "")),
            )
        )

    names = [c.name for c in configs]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate checker names: {sorted(dupes)}")
    defaults = [c.name for c in configs if c.default]
    if len(defaults) != 1:
        raise ValueError(
            f"exactly one checker must have default: true, found {len(defaults)}"
        )
    return configs


def load_checkers(
    path: str,
    *,
    fallback_provider: str,
    fallback_model: str,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    gemini_api_key: str = "",
    factory: Callable[..., GrammarProvider] = create_provider,
) -> Checkers:
    file = Path(path)
    if file.is_file():
        configs = _parse(file)
    else:
        # Absent — or a directory, which docker compose creates when the host
        # file does not exist. Either way: the pre-checkers.json behaviour.
        configs = [
            CheckerConfig(
                name="default",
                provider=fallback_provider,
                model=fallback_model,
                default=True,
            )
        ]

    providers = {
        c.name: factory(
            c.provider,
            c.model,
            anthropic_api_key=anthropic_api_key,
            openai_api_key=openai_api_key,
            gemini_api_key=gemini_api_key,
            base_url=c.base_url,
        )
        for c in configs
    }
    return Checkers(
        providers=providers,
        configs={c.name: c for c in configs},
        default=next(c.name for c in configs if c.default),
    )
```

- [ ] **Step 5: Run the suite** — `uv run task check`. Expected: PASS.

- [ ] **Step 6: Commit** — `git add -A backend && git commit -m "feat: load a named checker list from checkers.json"`

---

### Task 4: Result provenance and opinions in the store

**Files:**
- Modify: `backend/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Produces: `CheckResult.checker: str` and `CheckResult.opinions: list[dict]`, both in `to_dict()`; `ResultStore.broadcast(result)` (re-broadcast without re-adding), used by `add_and_broadcast` and by Task 6.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_store.py`; follow its existing style for constructing `CheckResult` and a fake websocket):

```python
def test_to_dict_carries_checker_and_opinions():
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="",
                    checker="terra")
    r.opinions.append({"checker": "qwen8", "has_issues": True, "status": "issues",
                       "types": ["grammar"], "issues": [], "correction": "", "diff": [],
                       "explanation": "", "has_ghost_marks": False, "timestamp": "t"})
    d = r.to_dict()
    assert d["checker"] == "terra"
    assert d["opinions"][0]["checker"] == "qwen8"
    assert "debug" not in d


@pytest.mark.asyncio
async def test_broadcast_resends_without_adding():
    store = ResultStore()
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    store.add(r)
    ws = AsyncMock()
    store.connect(ws)
    await store.broadcast(r)
    assert len(store.results) == 1
    ws.send_json.assert_awaited_once_with(r.to_dict())
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest backend/tests/test_store.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** In `CheckResult`, after `agent`:

```python
    # Which named checker produced the verdict, and any second opinions
    # attached later — one per checker name, shaped like the fields the
    # dashboard renders for the main verdict.
    checker: str = ""
    opinions: list[dict[str, Any]] = field(default_factory=list)
```

In `to_dict()`, after `"agent"`: `"checker": self.checker,` and after `"has_ghost_marks"`: `"opinions": [dict(o) for o in self.opinions],`. Split `add_and_broadcast`:

```python
    async def broadcast(self, result: CheckResult):
        data = result.to_dict()
        dead = []
        # Snapshot the set: sending yields to the event loop, which may
        # connect/disconnect clients and mutate _connections mid-iteration.
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    async def add_and_broadcast(self, result: CheckResult):
        self.add(result)
        await self.broadcast(result)
```

- [ ] **Step 4: Run the suite** — `uv run task check`. Expected: PASS.

- [ ] **Step 5: Commit** — `git add -A backend && git commit -m "feat: record the checker on a result and make room for opinions"`

---

### Task 5: Wire checkers into the app

**Files:**
- Modify: `backend/main.py` (lifespan, `/api/check`, `_run_check` → `_perform_check` split)
- Modify: `backend/tests/conftest.py` (the `provider` fixture)
- Test: `backend/tests/test_check.py`

**Interfaces:**
- Consumes: `load_checkers`/`Checkers` (Task 3), `CheckResult.checker` (Task 4).
- Produces: `app.state.checkers: Checkers` (replaces `app.state.provider`); `async _perform_check(provider, prompt, request_meta) -> tuple[dict, dict]` returning `(fields, debug)` where `fields` has exactly the keys `has_issues, explanation, status, types, issues, correction, diff` — reused verbatim by Task 6.

- [ ] **Step 1: Update the fixture** so every existing test runs against the new state shape. In `backend/tests/conftest.py`, replace the `provider` fixture (keep the name — existing tests depend on it):

```python
@pytest_asyncio.fixture
async def provider():
    from checkers import CheckerConfig, Checkers

    p = MagicMock()
    app.state.checkers = Checkers(
        providers={"default": p},
        configs={
            "default": CheckerConfig(
                name="default", provider="test", model="test-model", default=True
            )
        },
        default="default",
    )
    yield p
```

- [ ] **Step 2: Write the failing test** (append to `backend/tests/test_check.py`, using its existing pattern for driving `/api/check` and draining background tasks):

```python
@pytest.mark.asyncio
async def test_result_records_which_checker_ran(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    provider.check_grammar = AsyncMock(
        return_value=GrammarResult(has_issues=False, explanation="")
    )
    await client.post("/api/check", json={"prompt": "hi"},
                      headers={"Authorization": "Bearer tok"})
    await asyncio.gather(*app.state.background_tasks)
    result = store.results[-1]
    assert result.checker == "default"
    assert result.debug["request"]["checker"] == "default"
    assert result.debug["request"]["model"] == "test-model"
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest backend/tests/test_check.py -q`. Expected: the new test FAILS; others may fail on `app.state.provider` until Step 4.

- [ ] **Step 4: Implement in `backend/main.py`.** Lifespan — replace the `create_provider` call (and its import) with:

```python
    app.state.checkers = load_checkers(
        settings.checkers_file,
        fallback_provider=settings.provider,
        fallback_model=settings.model,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        gemini_api_key=settings.gemini_api_key,
    )
```

(import `load_checkers` from `checkers`; `create_provider` is no longer imported here). `/api/check` becomes:

```python
    checkers = request.app.state.checkers
    name = checkers.default
    cfg = checkers.configs[name]
    task = asyncio.create_task(
        _run_check(
            request.app.state.store,
            checkers.providers[name],
            username,
            body.prompt,
            body.project,
            body.agent,
            checker=name,
            provider_name=cfg.provider,
            model=cfg.model,
        )
    )
```

Split `_run_check`: everything between the `started = time.perf_counter()` and the two `CheckResult(...)` constructions moves into `_perform_check` — the existing try/except, `analyse` isolation and debug shapes move verbatim, with the two outcomes expressed as `fields`/`debug` pairs:

```python
async def _perform_check(provider, prompt: str, request_meta: dict) -> tuple[dict, dict]:
    """Run one checker over one prompt.

    Returns (fields, debug): fields is what a verdict looks like wherever it
    lands — a fresh CheckResult or an opinion on an existing one — and debug is
    the record that never rides the WebSocket.
    """
    started = time.perf_counter()
    try:
        result = await provider.check_grammar(prompt)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            analysis = analyse(prompt, result.correction)
        except Exception:
            # Observation only. A fault in it must not reach the except below
            # and turn a perfectly good verdict into an error result.
            analysis = {}
        fields = {
            "has_issues": result.has_issues,
            "explanation": result.explanation,
            "status": "issues" if result.has_issues else "clean",
            "types": result.types,
            "issues": result.issues,
            "correction": result.correction,
            "diff": analysis.get("diff", []),
        }
        debug = {
            "request": request_meta,
            "raw": result.raw,
            "derived": {"dropped_issues": result.dropped_issues},
            "timing": {"latency_ms": elapsed_ms, "usage": result.usage},
            "analysis": analysis,
        }
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        fields = {
            "has_issues": False,
            "explanation": f"Grammar check failed: {e}",
            "status": "error",
            "types": [],
            "issues": [],
            "correction": "",
            "diff": [],
        }
        # A failure previously left only the formatted message. The type is
        # what tells a timeout apart from a schema rejection.
        debug = {
            "request": request_meta,
            "error": {"type": type(e).__name__, "message": str(e)},
            "timing": {"latency_ms": elapsed_ms},
        }
    return fields, debug


async def _run_check(
    store: ResultStore,
    provider,
    username: str,
    prompt: str,
    project: str = "",
    agent: str = "",
    *,
    checker: str = "",
    provider_name: str = "",
    model: str = "",
):
    request_meta = {
        "checker": checker,
        "provider": provider_name,
        "model": model,
        "system_prompt_hash": SYSTEM_PROMPT_HASH,
    }
    fields, debug = await _perform_check(provider, prompt, request_meta)
    await store.add_and_broadcast(
        CheckResult(
            username=username, prompt=prompt, project=project, agent=agent,
            checker=checker, debug=debug, **fields,
        )
    )
```

- [ ] **Step 5: Run the whole suite** — `uv run task check`. Expected: PASS — the fixture change carries the old tests; fix any straggler that referenced `app.state.provider` directly.

- [ ] **Step 6: Commit** — `git add -A backend && git commit -m "feat: route every check through a named checker"`

---

### Task 6: The checkers list and second-opinion endpoints

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_opinions.py` (new)

**Interfaces:**
- Consumes: `_perform_check` (Task 5), `store.broadcast` (Task 4).
- Produces: `GET /api/checkers` → `{"checkers": [{"name": ..., "default": bool}]}`; `POST /api/results/{id}/checks` → 202/404/422, opinion dict keys: `checker, timestamp, has_ghost_marks` + the seven `fields` keys.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_opinions.py`, reusing conftest fixtures and the existing test style (auth header, `asyncio.gather(*app.state.background_tasks)` to drain):

```python
async def seed_result(store, checker="default"):
    r = CheckResult(username="u", prompt="lets go", has_issues=True,
                    explanation="", checker=checker)
    store.add(r)
    return r
```

Cases, each a separate test:
- `test_checkers_endpoint_lists_names`: with the `provider` fixture active, `GET /api/checkers` with a valid token → 200, `{"checkers": [{"name": "default", "default": True}]}`; without a token → 401.
- `test_unknown_result_is_404`: POST to `/api/results/999/checks` with `{"checker": "default"}` → 404.
- `test_unknown_checker_is_422`: seed a result; POST `{"checker": "nope"}` → 422.
- `test_own_checker_counts_as_attached`: seed with `checker="default"`; POST `{"checker": "default"}` → 422.
- `test_opinion_lands_and_rebroadcasts`: extend the fixture state in the test with a second checker (`Checkers` built by hand with `"second"` alongside `"default"`, its provider an `AsyncMock` returning a `GrammarResult(has_issues=False, explanation="")`); seed with `checker="default"`; POST `{"checker": "second"}` → 202; drain tasks; assert `store.results[-1].opinions[0]["checker"] == "second"`, `["status"] == "clean"`, opinion has no `raw` key, and `result.debug["opinions"]["second"]["request"]["checker"] == "second"`; assert a second POST of the same name → 422.
- `test_failed_opinion_is_an_error_opinion`: second checker's `check_grammar` raises; POST → 202; drained; opinion `status == "error"` and the result still broadcasts.

- [ ] **Step 2: Run to verify failure** — `uv run pytest backend/tests/test_opinions.py -q`. Expected: FAIL, 404s on the routes.

- [ ] **Step 3: Implement in `backend/main.py`:**

```python
class OpinionRequest(BaseModel):
    # Same slug rule as checker names in checkers.py.
    checker: str = Field(pattern=r"^[a-z0-9-]{1,32}$")


@app.get("/api/checkers")
async def list_checkers(request: Request, _username: str = Depends(require_username)):
    """The configured checkers, for the dashboard's "check with…" control."""
    configs = request.app.state.checkers.configs.values()
    return {"checkers": [{"name": c.name, "default": c.default} for c in configs]}


@app.post("/api/results/{result_id}/checks", status_code=202)
async def add_opinion(
    result_id: int,
    body: OpinionRequest,
    request: Request,
    _username: str = Depends(require_username),
):
    checkers = request.app.state.checkers
    if body.checker not in checkers.providers:
        raise HTTPException(status_code=422, detail="unknown checker")
    store = request.app.state.store
    result = next((r for r in store.results if r.id == result_id), None)
    if result is None:
        raise HTTPException(status_code=404, detail="not found")
    attached = {result.checker} | {o["checker"] for o in result.opinions}
    if body.checker in attached:
        raise HTTPException(status_code=422, detail="checker already ran on this result")
    task = asyncio.create_task(_run_opinion(store, checkers, result, body.checker))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return {"status": "accepted"}


async def _run_opinion(store: ResultStore, checkers, result: CheckResult, name: str):
    cfg = checkers.configs[name]
    request_meta = {
        "checker": name,
        "provider": cfg.provider,
        "model": cfg.model,
        "system_prompt_hash": SYSTEM_PROMPT_HASH,
    }
    fields, debug = await _perform_check(checkers.providers[name], result.prompt, request_meta)
    # Re-check under the running loop: two clicks can race the 422 guard, and
    # the second to finish must not attach a duplicate.
    if name in {o["checker"] for o in result.opinions}:
        return
    result.opinions.append(
        {
            "checker": name,
            "timestamp": datetime.now(UTC).isoformat(),
            "has_ghost_marks": bool((debug.get("analysis") or {}).get("ghost_marks")),
            **fields,
        }
    )
    if result.debug is None:
        result.debug = {}
    result.debug.setdefault("opinions", {})[name] = debug
    await store.broadcast(result)
```

(add `from datetime import UTC, datetime` to the imports.)

- [ ] **Step 4: Run the suite** — `uv run task check`. Expected: PASS.

- [ ] **Step 5: Commit** — `git add -A backend && git commit -m "feat: attach a second opinion to an existing result"`

---

### Task 7: Dashboard — replace-in-place, checker badge, "check with…", opinions

**Files:**
- Modify: `frontend/static/app.js`
- Modify: `frontend/static/style.css`

**Interfaces:**
- Consumes: `to_dict()` now carrying `checker` and `opinions`; `GET /api/checkers`; `POST /api/results/{id}/checks`.

The frontend has no test suite; correctness here is `node --check` plus Task 9's browser verification.

- [ ] **Step 1: Track entries by id.** Replace `const seen = new Set()` with `const entries = new Map()` (id → element). In `addEntry`: the run-reset branch calls `entries.clear()`; the dedup branch becomes replace-in-place:

```javascript
    const existing = entries.get(data.id);
```

Build the entry element exactly as today, then instead of unconditional `feed.prepend(entry)`:

```javascript
    if (existing) {
        // A re-broadcast: the result gained an opinion. Same position, new
        // content — an open debug panel is dropped rather than kept stale.
        existing.replaceWith(entry);
    } else {
        feed.prepend(entry);
    }
    entries.set(data.id, entry);
```

(The post-insert measurements — clip detection, mark colouring — already run after this point; keep them after the insert/replace.)

- [ ] **Step 2: Fetch the checker list once at startup.** Alongside `loadHistory()`:

```javascript
// The configured checkers, for the "check with…" control. Loaded once; a
// failure just means the control never appears, which is the right degradation.
let availableCheckers = [];

async function loadCheckers() {
    try {
        const resp = await fetch("/api/checkers", {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (resp.ok) {
            availableCheckers = (await resp.json()).checkers || [];
        }
    } catch (e) {
        // Leave the list empty.
    }
}
```

Call `loadCheckers()` where `loadHistory()` is first triggered (same lifecycle point).

- [ ] **Step 3: Render the checker badge and the control.** In `addEntry`'s header template, after the agent tag:

```javascript
    const checkerTag = data.checker
        ? `<span class="checker">${escapeHtml(data.checker)}</span>`
        : "";
```

After the `body` computation, build the offer list — checkers not yet attached, never on error entries:

```javascript
    const attached = new Set([data.checker, ...(data.opinions || []).map((o) => o.checker)]);
    const offers = data.status === "error" ? [] : availableCheckers.filter((c) => !attached.has(c.name));
    const opinionControls = offers.length
        ? `<div class="opinion-offer">${offers
              .map(
                  (c) =>
                      `<button type="button" class="opinion-link" data-id="${data.id}" data-checker="${escapeHtml(c.name)}">check with ${escapeHtml(c.name)}</button>`
              )
              .join("")}</div>`
        : "";
```

- [ ] **Step 4: Render opinions.** Factor the existing `issueRows` + `correctionHtml` construction into a helper `renderVerdict(data)` returning that HTML fragment (it reads only `data.issues`, `data.diff`, `data.explanation` — the opinion dicts carry the same keys), and use it for both the main body and:

```javascript
    const opinionBlocks = (data.opinions || [])
        .map((o) => {
            const badgeClass = o.status === "error" ? "error" : o.has_issues ? "issues" : "clean";
            const badgeText = o.status === "error" ? "error" : o.has_issues ? "issues found" : "clean";
            return `<div class="opinion">
                <div class="opinion-header">
                    <span class="checker">${escapeHtml(o.checker)}</span>
                    <span class="badge ${badgeClass}">${badgeText}</span>
                </div>
                ${renderVerdict(o)}
            </div>`;
        })
        .join("");
```

Append `${opinionBlocks}${opinionControls}` to the entry template after `${body}`.

- [ ] **Step 5: Handle the click.** Extend the existing delegated `feed` listener (before the debug-link branch):

```javascript
    const opinionLink = event.target.closest(".opinion-link");
    if (opinionLink) {
        opinionLink.disabled = true;
        opinionLink.textContent = "checking…";
        try {
            const resp = await fetch(`/api/results/${opinionLink.dataset.id}/checks`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ checker: opinionLink.dataset.checker }),
            });
            if (!resp.ok) {
                opinionLink.textContent = `failed (${resp.status})`;
            }
            // On success the re-broadcast replaces the whole entry.
        } catch (e) {
            opinionLink.disabled = false;
            opinionLink.textContent = `check with ${opinionLink.dataset.checker}`;
        }
        return;
    }
```

- [ ] **Step 6: Styles.** In `style.css`, using only existing tokens (`--border`, `--muted`, `--surface`, and `color-mix` with `--tint` — no new hues, so no new theme-block entries needed):

```css
/* Which checker produced a verdict — mirrors .project's quiet chip look. */
.checker {
    font-size: 0.75rem;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.05rem 0.4rem;
}

/* A second opinion nests inside the entry, visually subordinate to it. */
.opinion {
    margin-top: 0.6rem;
    padding: 0.6rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
}

.opinion-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
}

.opinion-offer {
    margin-top: 0.6rem;
}

.opinion-link {
    font-size: 0.75rem;
    color: var(--muted);
    background: none;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.15rem 0.5rem;
    cursor: pointer;
}

.opinion-link:disabled {
    cursor: default;
    opacity: 0.7;
}
```

Match the exact property style of the existing `.project` / `.debug-link` rules when writing these — copy their conventions, not this sketch, where they differ.

- [ ] **Step 7: Syntax check** — `node --check frontend/static/app.js`. Expected: silence.

- [ ] **Step 8: Commit** — `git add frontend && git commit -m "feat: show second opinions and offer them per result"`

---

### Task 8: Config surface — example file, gitignore, compose, docs

**Files:**
- Create: `checkers.json.example`, `checkers.json` (local only, gitignored)
- Modify: `.gitignore`, `docker-compose.yml`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: The example** — `checkers.json.example`:

```json
{
  "checkers": [
    { "name": "cloud", "provider": "openai", "model": "gpt-5.6-terra", "default": true },
    { "name": "local", "provider": "openai", "model": "qwen3:4b",
      "base_url": "http://host.docker.internal:11434/v1" }
  ]
}
```

- [ ] **Step 2: gitignore + compose.** Add `checkers.json` to `.gitignore` (after `tokens.json`). In `docker-compose.yml`, under the backend's `volumes`, add `- ./checkers.json:/app/checkers.json:ro` with the comment: `# Optional; without the host file compose mounts a directory, which the loader treats as absent.`

- [ ] **Step 3: The real config** — write `checkers.json` (gitignored) for this machine: `terra` (openai, `gpt-5.6-terra`, default), `luna` (openai, `gpt-5.6-luna`), `qwen` (openai, `qwen3:4b`, base_url `http://host.docker.internal:11434/v1`).

- [ ] **Step 4: README.** In Quick start step 1, after the `tokens.json` copy: `cp checkers.json.example checkers.json  # optional — omit it and PROVIDER/MODEL from .env apply`. Add a short section after **Supported providers** titled **Multiple checkers**, stating: the file's shape (name/provider/model/default/base_url), exactly-one-default rule, that the hook always uses the default, that other checkers appear as a "check with…" button on each dashboard entry, and that a local Ollama model is just an `openai` entry with a `base_url` (no key needed). Include the JSON example from Step 1 verbatim.

- [ ] **Step 5: CLAUDE.md.** Under Key conventions, add: `checkers.json` follows the `tokens.json` pattern (gitignored, `.example` committed, loaded at startup, restart after changes); exactly one `default: true` or the backend refuses to start; a missing file falls back to `PROVIDER`/`MODEL`; opinions live on the parent result and their debug records under `debug["opinions"]`, which stays off the WebSocket like all debug.

- [ ] **Step 6: Verify and commit**

```bash
uv run task check
node --check frontend/static/app.js
git add .gitignore docker-compose.yml README.md CLAUDE.md checkers.json.example
git commit -m "docs: describe the named checker configuration"
```

(`git status --short` must show `checkers.json` as untracked-and-ignored, i.e. not show it at all.)

---

### Task 9: End-to-end verification on the live stack

No new code — proof the pieces meet. Uses the project's `verify-dashboard` skill conventions.

- [ ] **Step 1: Rebuild with the real config** — from the main checkout (or with `.env`/`tokens.json`/`checkers.json` symlinked and `-p hoshi` from a worktree): `docker compose -p hoshi up -d --build`. The store clears; that is expected.

- [ ] **Step 2: Startup validation proof.** Temporarily break `checkers.json` (second `default: true`), `docker compose -p hoshi up -d backend`, confirm the backend container exits with the ValueError in `docker compose -p hoshi logs backend`. Restore the file, bring it back up. A guard that cannot be seen failing has not been proven to exist.

- [ ] **Step 3: Seed and verify in the browser** at the dashboard: seed one prompt via the API (any fixture prompt from the verify-dashboard skill, never live text). Confirm: the entry shows its checker badge (`terra`); a "check with luna" (and `qwen`) button is present; clicking it shows "checking…", then the entry re-renders in place with a nested opinion block labelled `luna` carrying its own badge and diff; the button for `luna` is gone and `qwen`'s remains; the debug panel under the toggle shows `opinions.luna` in the raw JSON; no `debug` key in the WebSocket frames (check DevTools → Network → WS).

- [ ] **Step 4: The local checker, if Ollama is up** — click "check with qwen": an opinion appears (or an error opinion if the model misbehaves — also a valid render to verify). If Ollama is not running, the error opinion path is the verification.

- [ ] **Step 5: Restart-reset proof.** `docker compose -p hoshi restart backend`, seed one prompt, confirm the dashboard dropped the old entries and shows the new one (the `run_id` reset path still works with the Map).

---

## Execution notes

- Tasks 2–6 are backend-only and sequential (each consumes the previous task's interface). Task 7 depends on 6; Task 8 on 7; Task 9 on everything.
- Task 1 gates the plan but writes no production code; if it reports BLOCKED, stop before Task 2.
- Work in a worktree (superpowers:using-git-worktrees); `git rebase main` immediately after creating it — worktrees here branch from `origin/main`, which may trail local `main`.
