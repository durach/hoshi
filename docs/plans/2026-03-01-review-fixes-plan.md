# Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 13 findings from the CC code review and Codex review report.

**Architecture:** Changes span backend (Python/FastAPI), frontend (HTML/JS/CSS), and Docker config. The most invasive change is #9 (lifespan refactor of main.py), which restructures how the app initializes. All other fixes are localized. Order matters: do the lifespan refactor (#9) early since it changes how tests and routes work, then layer the other fixes on top.

**Tech Stack:** Python 3.12, FastAPI, pytest, vanilla JS, nginx, Docker

**Design doc:** `docs/plans/2026-03-01-review-fixes-design.md`

---

### Task 1: Split test deps from production requirements (#10)

Simplest change, zero risk, do it first to warm up.

**Files:**
- Modify: `backend/requirements.txt:8-10`
- Create: `backend/requirements-dev.txt`

**Step 1: Create `requirements-dev.txt`**

```
# requirements-dev.txt
-r requirements.txt
pytest>=8.0,<9.0
pytest-asyncio>=0.25.0,<1.0
httpx>=0.28.0,<1.0
```

**Step 2: Remove test deps from `requirements.txt`**

Remove lines 8-10 (`pytest`, `pytest-asyncio`, `httpx`) from `backend/requirements.txt`. File should end after `pydantic-settings`.

**Step 3: Verify tests still run**

```bash
cd backend && uv pip install -r requirements-dev.txt && python -m pytest -v
```

Expected: All tests pass (requirements-dev.txt includes `-r requirements.txt`).

**Step 4: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt
git commit -m "chore: split test deps into requirements-dev.txt (#10)"
```

---

### Task 2: Extract SYSTEM_PROMPT to providers/__init__.py (#8)

**Files:**
- Modify: `backend/providers/__init__.py:1-12`
- Modify: `backend/providers/anthropic.py:7-10`
- Modify: `backend/providers/openai.py:7-10`
- Modify: `backend/providers/gemini.py:7-10`

**Step 1: Add SYSTEM_PROMPT to `providers/__init__.py`**

Add after the `GrammarResult` dataclass (after line 8):

```python
SYSTEM_PROMPT = (
    "Check the grammar of the following text. Explain issues if you find. "
    'Respond with JSON: {"has_issues": true/false, "explanation": "markdown text"}'
)
```

**Step 2: Update all three providers**

In each of `anthropic.py`, `openai.py`, `gemini.py`:
- Remove the `SYSTEM_PROMPT = (...)` definition (lines 7-10).
- Change the import line to include `SYSTEM_PROMPT`:
  - `from providers import GrammarResult` → `from providers import GrammarResult, SYSTEM_PROMPT`

**Step 3: Run tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass.

**Step 4: Commit**

```bash
git add backend/providers/
git commit -m "refactor: extract SYSTEM_PROMPT to providers/__init__.py (#8)"
```

---

### Task 3: Add JSON parse handling to providers (#5)

**Files:**
- Modify: `backend/providers/__init__.py`
- Modify: `backend/providers/anthropic.py:25`
- Modify: `backend/providers/openai.py:26`
- Modify: `backend/providers/gemini.py:26`
- Create: `backend/tests/test_providers.py`

**Step 1: Add `parse_provider_json` helper to `providers/__init__.py`**

Add after `SYSTEM_PROMPT`:

```python
import json
import re


def parse_provider_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Provider returned invalid JSON: {e}") from e
```

**Step 2: Write failing test**

Create `backend/tests/test_providers.py`:

```python
import pytest

from providers import parse_provider_json


def test_parse_clean_json():
    raw = '{"has_issues": false, "explanation": ""}'
    assert parse_provider_json(raw) == {"has_issues": False, "explanation": ""}


def test_parse_markdown_fenced_json():
    raw = '```json\n{"has_issues": true, "explanation": "bad grammar"}\n```'
    assert parse_provider_json(raw) == {"has_issues": True, "explanation": "bad grammar"}


def test_parse_invalid_json_raises_valueerror():
    with pytest.raises(ValueError, match="Provider returned invalid JSON"):
        parse_provider_json("Sure! Here is the result...")
```

**Step 3: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_providers.py -v
```

Expected: 3 pass.

**Step 4: Update providers to use `parse_provider_json`**

In each of `anthropic.py`, `openai.py`, `gemini.py`:
- Change import: `from providers import GrammarResult, SYSTEM_PROMPT` → `from providers import GrammarResult, SYSTEM_PROMPT, parse_provider_json`
- Remove `import json` (top of file).
- Replace `data = json.loads(...)` with `data = parse_provider_json(...)`:
  - `anthropic.py:25`: `data = parse_provider_json(response.content[0].text)`
  - `openai.py:26`: `data = parse_provider_json(response.choices[0].message.content)`
  - `gemini.py:26`: `data = parse_provider_json(response.text)`

**Step 5: Run all tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add backend/providers/ backend/tests/test_providers.py
git commit -m "fix: handle markdown fences and invalid JSON from providers (#5)"
```

---

### Task 4: Fix disconnect ValueError and use set for connections (#6)

**Files:**
- Modify: `backend/store.py:30,36,38-39,51`
- Modify: `backend/tests/test_check.py` (if tests touch store connections)

**Step 1: Write failing test**

Add to a new file `backend/tests/test_store.py`:

```python
from store import CheckResult, ResultStore


def test_disconnect_idempotent():
    """Disconnecting a websocket twice should not raise."""
    store = ResultStore()
    sentinel = object()
    store.connect(sentinel)
    store.disconnect(sentinel)
    store.disconnect(sentinel)  # should not raise
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_store.py::test_disconnect_idempotent -v
```

Expected: FAIL with `ValueError`.

**Step 3: Change `_connections` to set in `store.py`**

In `backend/store.py`:
- Line 30: `self._connections: list = []` → `self._connections: set = set()`
- Line 36: `self._connections.append(websocket)` → `self._connections.add(websocket)`
- Line 39: `self._connections.remove(websocket)` → `self._connections.discard(websocket)`
- Line 51: `self._connections.remove(ws)` → `self._connections.discard(ws)`

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_store.py -v
```

Expected: PASS.

**Step 5: Run all tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add backend/store.py backend/tests/test_store.py
git commit -m "fix: make disconnect idempotent by using set for connections (#6)"
```

---

### Task 5: Cap in-memory results at 1000 (#12)

**Files:**
- Modify: `backend/store.py:32-33`
- Modify: `backend/tests/test_store.py`

**Step 1: Write failing test**

Add to `backend/tests/test_store.py`:

```python
def test_results_capped_at_max():
    store = ResultStore()
    for i in range(1005):
        store.add(CheckResult(
            username="u", prompt=f"p{i}", has_issues=False, explanation="",
        ))
    assert len(store.results) == 1000
    assert store.results[0].prompt == "p5"  # oldest 5 evicted
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_store.py::test_results_capped_at_max -v
```

Expected: FAIL — `len(store.results)` is 1005.

**Step 3: Implement cap in `store.py`**

In `ResultStore`:

```python
MAX_RESULTS = 1000

def add(self, result: CheckResult):
    self.results.append(result)
    if len(self.results) > MAX_RESULTS:
        self.results = self.results[-MAX_RESULTS:]
```

Add `MAX_RESULTS = 1000` as a module-level constant above `ResultStore`.

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_store.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add backend/store.py backend/tests/test_store.py
git commit -m "fix: cap in-memory results at 1000 entries (#12)"
```

---

### Task 6: Add status field to CheckResult and error state (#7)

**Files:**
- Modify: `backend/store.py:6-11,17-24`
- Modify: `backend/main.py:58-65`
- Modify: `frontend/static/app.js:30-31,40`
- Modify: `frontend/static/style.css:55`
- Modify: `backend/tests/test_store.py`

**Step 1: Write failing test**

Add to `backend/tests/test_store.py`:

```python
def test_check_result_status_derived_from_has_issues():
    clean = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    assert clean.status == "clean"

    issues = CheckResult(username="u", prompt="p", has_issues=True, explanation="bad")
    assert issues.status == "issues"


def test_check_result_explicit_error_status():
    error = CheckResult(
        username="u", prompt="p", has_issues=False, explanation="fail", status="error",
    )
    assert error.status == "error"


def test_check_result_status_in_dict():
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    d = r.to_dict()
    assert d["status"] == "clean"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_store.py::test_check_result_status_derived_from_has_issues -v
```

Expected: FAIL — no `status` attribute.

**Step 3: Add status field to `CheckResult` in `store.py`**

```python
@dataclass
class CheckResult:
    username: str
    prompt: str
    has_issues: bool
    explanation: str
    status: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.status:
            self.status = "issues" if self.has_issues else "clean"

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "prompt": self.prompt,
            "has_issues": self.has_issues,
            "explanation": self.explanation,
            "status": self.status,
            "timestamp": self.timestamp,
        }
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_store.py -v
```

Expected: All pass.

**Step 5: Update error path in `main.py`**

In `_run_check`, change the except block (lines 58-65):

```python
    except Exception as e:
        error_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=False,
            explanation=f"Grammar check failed: {e}",
            status="error",
        )
        await store.add_and_broadcast(error_result)
```

(After the lifespan refactor in Task 8, `store` will be accessed differently — but at this point it's still module-level, so this is correct for now.)

**Step 6: Update frontend `app.js`**

Replace the badge logic (lines 30-31) with:

```javascript
const badgeClass = data.status === "error" ? "error" : data.has_issues ? "issues" : "clean";
const badgeText = data.status === "error" ? "error" : data.has_issues ? "issues found" : "clean";
```

Also update the explanation rendering (line 40) — show explanation for errors too:

```javascript
${data.has_issues || data.status === "error" ? `<div class="explanation">${marked.parse(data.explanation)}</div>` : ""}
```

**Step 7: Add CSS for error badge**

Add after `.badge.issues` in `style.css`:

```css
.badge.error { background: #d29922; color: #fff; }
```

**Step 8: Run backend tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass.

**Step 9: Commit**

```bash
git add backend/store.py backend/main.py backend/tests/test_store.py frontend/static/app.js frontend/static/style.css
git commit -m "fix: add explicit error status to CheckResult and dashboard (#7)"
```

---

### Task 7: Use HTTPException instead of JSONResponse (#13)

**Files:**
- Modify: `backend/main.py:1-4,42`

**Step 1: Update import and error response**

In `main.py`:
- Add `HTTPException` to the FastAPI import: `from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect`
- Remove `JSONResponse` import: remove `from fastapi.responses import JSONResponse`
- Line 42: Replace `return JSONResponse(status_code=401, content={"error": "unauthorized"})` with `raise HTTPException(status_code=401, detail="unauthorized")`

**Step 2: Run tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass (test_check_invalid_token and test_check_missing_auth still expect 401).

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "refactor: use HTTPException instead of JSONResponse for 401 (#13)"
```

---

### Task 8: Fix asyncio.create_task GC issue (#4)

**Files:**
- Modify: `backend/main.py:1,44`

**Step 1: Add background task set and fix create_task**

In `main.py`, add after the imports (before `settings = Settings()`):

```python
_background_tasks: set[asyncio.Task] = set()
```

Replace line 44 (`asyncio.create_task(_run_check(username, body.prompt))`) with:

```python
    task = asyncio.create_task(_run_check(username, body.prompt))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
```

**Step 2: Run tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass.

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "fix: hold strong references to background tasks (#4)"
```

---

### Task 9: Lifespan refactor — eliminate module-level side effects (#9, #11)

This is the most invasive change. It restructures `main.py`, `conftest.py`, and `test_check.py`.

**Files:**
- Modify: `backend/main.py` (full rewrite)
- Modify: `backend/tests/conftest.py` (full rewrite)
- Modify: `backend/tests/test_check.py:1-17`
- Modify: `backend/tests/test_health.py` (minor)

**Step 1: Rewrite `main.py` with lifespan**

```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from auth import TokenAuth
from config import Settings
from providers import create_provider
from store import CheckResult, ResultStore

_background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.store = ResultStore()
    app.state.auth = TokenAuth(settings.tokens_file)
    app.state.provider = create_provider(
        settings.provider,
        settings.model,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        gemini_api_key=settings.gemini_api_key,
    )
    yield


app = FastAPI(title="Hoshi", lifespan=lifespan)


class CheckRequest(BaseModel):
    prompt: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/check", status_code=202)
async def check(
    request: Request,
    body: CheckRequest,
    authorization: str = Header(default=""),
):
    token = authorization.removeprefix("Bearer ").strip()
    username = request.app.state.auth.validate(token)
    if not username:
        raise HTTPException(status_code=401, detail="unauthorized")

    task = asyncio.create_task(
        _run_check(request.app.state.store, request.app.state.provider, username, body.prompt)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "accepted"}


async def _run_check(store: ResultStore, provider, username: str, prompt: str):
    try:
        result = await provider.check_grammar(prompt)
        check_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=result.has_issues,
            explanation=result.explanation,
        )
        await store.add_and_broadcast(check_result)
    except Exception as e:
        error_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=False,
            explanation=f"Grammar check failed: {e}",
            status="error",
        )
        await store.add_and_broadcast(error_result)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket.app.state.store.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket.app.state.store.disconnect(websocket)
```

**Step 2: Rewrite `conftest.py`**

No more patching SDK constructors before import. Create app with test config directly.

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock

from auth import TokenAuth
from config import Settings
from store import ResultStore
from main import app


@pytest_asyncio.fixture
async def store():
    s = ResultStore()
    app.state.store = s
    yield s


@pytest_asyncio.fixture
async def auth():
    a = TokenAuth.__new__(TokenAuth)
    a._tokens = {}
    app.state.auth = a
    yield a


@pytest_asyncio.fixture
async def provider():
    p = MagicMock()
    app.state.provider = p
    yield p


@pytest_asyncio.fixture
async def client(store, auth, provider):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

**Step 3: Rewrite `test_check.py`**

Remove the duplicate `client` fixture. Use individual fixtures from conftest.

```python
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_check_returns_202(client, auth):
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.post(
            "/api/check",
            json={"prompt": "He go to store"},
            headers={"Authorization": "Bearer tok_test"},
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_check_invalid_token(client, auth):
    with patch.object(auth, "validate", return_value=None):
        resp = await client.post(
            "/api/check",
            json={"prompt": "Hello"},
            headers={"Authorization": "Bearer invalid"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_missing_auth(client):
    resp = await client.post("/api/check", json={"prompt": "Hello"})
    assert resp.status_code == 401
```

**Step 4: Verify `test_health.py` still works**

`test_health.py` uses the `client` fixture — it should work as-is since the new conftest `client` yields just the client object.

**Step 5: Run all tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass. If SDK import issues arise, the lifespan defers provider creation to startup, so SDK constructors are never called during import.

**Step 6: Commit**

```bash
git add backend/main.py backend/tests/conftest.py backend/tests/test_check.py
git commit -m "refactor: use FastAPI lifespan for initialization, fix duplicate fixture (#9, #11)"
```

---

### Task 10: XSS fix — add DOMPurify (#1)

**Files:**
- Modify: `frontend/static/index.html:8`
- Modify: `frontend/static/app.js:40`

**Step 1: Add DOMPurify script tag to `index.html`**

After the marked.js script tag (line 8), add:

```html
<script src="https://cdn.jsdelivr.net/npm/dompurify/dist/purify.min.js"></script>
```

**Step 2: Sanitize marked output in `app.js`**

Change the explanation line (line 40) from:

```javascript
${data.has_issues || data.status === "error" ? `<div class="explanation">${marked.parse(data.explanation)}</div>` : ""}
```

to:

```javascript
${data.has_issues || data.status === "error" ? `<div class="explanation">${DOMPurify.sanitize(marked.parse(data.explanation))}</div>` : ""}
```

**Step 3: Manual test** (optional, requires Docker)

```bash
docker compose up -d --build
```

Open `http://localhost:8080`, verify dashboard loads with no console errors.

**Step 4: Commit**

```bash
git add frontend/static/index.html frontend/static/app.js
git commit -m "fix: sanitize marked output with DOMPurify to prevent XSS (#1)"
```

---

### Task 11: WebSocket authentication (#2)

**Files:**
- Modify: `backend/main.py` (websocket endpoint)
- Modify: `frontend/static/index.html`
- Modify: `frontend/static/app.js:5-6`

**Step 1: Add token query param to WebSocket endpoint**

In `main.py`, update the websocket endpoint:

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    username = websocket.app.state.auth.validate(token)
    if not username:
        await websocket.close(code=4401, reason="unauthorized")
        return
    await websocket.accept()
    websocket.app.state.store.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket.app.state.store.disconnect(websocket)
```

Add `Query` to the FastAPI import if not already there (it was added in the Task 9 rewrite).

**Step 2: Add meta tag placeholder to `index.html`**

Add before the `<title>` tag:

```html
<meta name="ws-token" content="__WS_TOKEN__">
```

**Step 3: Update `app.js` to use token**

Change the `connect` function:

```javascript
function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const token = document.querySelector('meta[name="ws-token"]')?.content || "";
    const ws = new WebSocket(`${proto}//${location.host}/ws?token=${token}`);
```

**Step 4: Commit**

```bash
git add backend/main.py frontend/static/index.html frontend/static/app.js
git commit -m "feat: require token auth for WebSocket connections (#2)"
```

---

### Task 12: Move dashboard password out of image layer (#3)

**Files:**
- Modify: `frontend/Dockerfile`
- Create: `frontend/entrypoint.sh`
- Rename: `frontend/static/index.html` → used as template
- Modify: `docker-compose.yml`

**Step 1: Create `frontend/entrypoint.sh`**

```bash
#!/bin/sh
set -e

# Generate htpasswd at runtime
htpasswd -cb /etc/nginx/.htpasswd "${DASHBOARD_USER:-admin}" "${DASHBOARD_PASSWORD:-changeme}"

# Inject WS_TOKEN into HTML template
export WS_TOKEN="${WS_TOKEN:-}"
envsubst '${WS_TOKEN}' < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html

exec nginx -g 'daemon off;'
```

**Step 2: Update `frontend/Dockerfile`**

```dockerfile
FROM nginx:alpine

RUN apk add --no-cache apache2-utils

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY static/ /usr/share/nginx/html/
RUN mv /usr/share/nginx/html/index.html /usr/share/nginx/html/index.html.template

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
```

**Step 3: Update `docker-compose.yml`**

```yaml
services:
  backend:
    build: ./backend
    env_file: .env
    volumes:
      - ./tokens.json:/app/tokens.json:ro
    expose:
      - "8000"

  frontend:
    build: ./frontend
    environment:
      - DASHBOARD_USER=${DASHBOARD_USER:-admin}
      - DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD:-changeme}
      - WS_TOKEN=${WS_TOKEN:-}
    ports:
      - "8080:80"
    depends_on:
      - backend
```

Note: `DASHBOARD_USER` and `DASHBOARD_PASSWORD` are now runtime env vars (not build args). `WS_TOKEN` must match a token in `tokens.json`.

**Step 4: Manual test** (requires Docker)

```bash
WS_TOKEN=<your-token> docker compose up -d --build
```

Verify:
- Dashboard loads behind basic auth
- WebSocket connects (check browser console)
- `docker history` for frontend image should NOT contain the password

**Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/entrypoint.sh docker-compose.yml
git commit -m "fix: generate htpasswd and inject WS token at runtime (#3, #2)"
```

---

### Task 13: Final verification

**Step 1: Run all backend tests**

```bash
cd backend && python -m pytest -v
```

Expected: All pass.

**Step 2: Docker integration test**

```bash
docker compose up -d --build
curl -s http://localhost:8080/api/health
```

Expected: `{"status":"ok"}`.

**Step 3: Review all changes**

```bash
git log --oneline main..HEAD
```

Verify 12 commits covering all 13 findings.
