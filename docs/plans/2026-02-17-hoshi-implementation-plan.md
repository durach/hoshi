# Hoshi Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a grammar teaching tool that hooks into Claude Code, checks prompt grammar via configurable LLM providers, and displays results on a real-time web dashboard.

**Architecture:** Two Docker containers — FastAPI backend (API + WebSocket + LLM calls) and nginx frontend (static dashboard + reverse proxy). Async Claude Code hook sends prompts to the backend; results broadcast to dashboard via WebSocket.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, anthropic/openai/google-genai SDKs, pytest, httpx, nginx, vanilla HTML/JS/CSS, Docker Compose.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/providers/__init__.py`
- Create: `backend/main.py` (empty app placeholder)
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

**Step 1: Create directory structure**

```bash
mkdir -p backend/providers backend/tests frontend/static hook
```

**Step 2: Write `backend/requirements.txt`**

```
fastapi>=0.115.0,<1.0
uvicorn[standard]>=0.34.0,<1.0
anthropic>=0.52.0,<1.0
openai>=1.82.0,<2.0
google-genai>=1.14.0,<2.0
pydantic>=2.0,<3.0
pydantic-settings>=2.0,<3.0
pytest>=8.0,<9.0
pytest-asyncio>=0.25.0,<1.0
httpx>=0.28.0,<1.0
```

**Step 3: Write `backend/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    tokens_file: str = "tokens.json"

    model_config = {"env_file": ".env"}
```

**Step 4: Write minimal `backend/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Hoshi")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

**Step 5: Write `backend/tests/conftest.py`**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

**Step 6: Write empty `__init__.py` files**

```bash
touch backend/providers/__init__.py backend/tests/__init__.py
```

**Step 7: Install dependencies and verify**

```bash
cd backend && pip install -r requirements.txt
```

**Step 8: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend project structure"
```

---

### Task 2: Health Endpoint Test

**Files:**
- Create: `backend/tests/test_health.py`

**Step 1: Write the test**

```python
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

**Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_health.py
git commit -m "test: add health endpoint test"
```

---

### Task 3: Token Auth

**Files:**
- Create: `backend/auth.py`
- Create: `backend/tests/test_auth.py`
- Create: `backend/tests/fixtures/tokens.json`

**Step 1: Create test fixtures**

Create `backend/tests/fixtures/tokens.json`:

```json
{
  "tok_test_abc": "alice",
  "tok_test_def": "bob"
}
```

**Step 2: Write the failing test**

```python
import pytest

from auth import TokenAuth


@pytest.fixture
def auth():
    return TokenAuth("tests/fixtures/tokens.json")


def test_valid_token(auth):
    assert auth.validate("tok_test_abc") == "alice"


def test_invalid_token(auth):
    assert auth.validate("tok_invalid") is None


def test_empty_token(auth):
    assert auth.validate("") is None
```

**Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL — `auth` module not found

**Step 4: Write implementation**

Create `backend/auth.py`:

```python
import json
from pathlib import Path


class TokenAuth:
    def __init__(self, tokens_file: str):
        path = Path(tokens_file)
        if path.exists():
            self._tokens: dict[str, str] = json.loads(path.read_text())
        else:
            self._tokens = {}

    def validate(self, token: str) -> str | None:
        if not token:
            return None
        return self._tokens.get(token)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/auth.py backend/tests/test_auth.py backend/tests/fixtures/
git commit -m "feat: add token authentication"
```

---

### Task 4: LLM Provider Protocol and Anthropic Provider

**Files:**
- Modify: `backend/providers/__init__.py`
- Create: `backend/providers/anthropic.py`
- Create: `backend/tests/test_providers.py`

**Step 1: Write the failing test**

Create `backend/tests/test_providers.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from providers import GrammarResult
from providers.anthropic import AnthropicProvider


@pytest.mark.asyncio
async def test_anthropic_provider_parses_response():
    provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-4-5-20250929")

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text='{"has_issues": true, "explanation": "Use *goes* instead of *go*."}')
    ]

    with patch.object(provider._client.messages, "create", new_callable=AsyncMock, return_value=mock_response):
        result = await provider.check_grammar("He go to the store")

    assert result.has_issues is True
    assert "goes" in result.explanation


@pytest.mark.asyncio
async def test_anthropic_provider_no_issues():
    provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-4-5-20250929")

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text='{"has_issues": false, "explanation": "No issues found."}')
    ]

    with patch.object(provider._client.messages, "create", new_callable=AsyncMock, return_value=mock_response):
        result = await provider.check_grammar("The cat sat on the mat.")

    assert result.has_issues is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_providers.py -v`
Expected: FAIL — imports fail

**Step 3: Write the provider protocol**

Update `backend/providers/__init__.py`:

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class GrammarResult:
    has_issues: bool
    explanation: str


class GrammarProvider(Protocol):
    async def check_grammar(self, text: str) -> GrammarResult: ...
```

**Step 4: Write the Anthropic provider**

Create `backend/providers/anthropic.py`:

```python
import json

import anthropic

from providers import GrammarResult

SYSTEM_PROMPT = (
    "Check the grammar of the following text. Explain issues if you find. "
    'Respond with JSON: {"has_issues": true/false, "explanation": "markdown text"}'
)


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        data = json.loads(response.content[0].text)
        return GrammarResult(
            has_issues=data["has_issues"],
            explanation=data.get("explanation", ""),
        )
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_providers.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/providers/ backend/tests/test_providers.py
git commit -m "feat: add LLM provider protocol and Anthropic implementation"
```

---

### Task 5: OpenAI and Gemini Providers

**Files:**
- Create: `backend/providers/openai.py`
- Create: `backend/providers/gemini.py`
- Modify: `backend/tests/test_providers.py`

**Step 1: Write failing tests**

Append to `backend/tests/test_providers.py`:

```python
from providers.openai import OpenAIProvider
from providers.gemini import GeminiProvider


@pytest.mark.asyncio
async def test_openai_provider_parses_response():
    provider = OpenAIProvider(api_key="fake-key", model="gpt-4o")

    mock_choice = MagicMock()
    mock_choice.message.content = '{"has_issues": true, "explanation": "Fix grammar."}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(
        provider._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await provider.check_grammar("He go to store")

    assert result.has_issues is True


@pytest.mark.asyncio
async def test_gemini_provider_parses_response():
    provider = GeminiProvider(api_key="fake-key", model="gemini-2.0-flash")

    mock_response = MagicMock()
    mock_response.text = '{"has_issues": false, "explanation": "All good."}'

    with patch.object(
        provider._client.models, "generate_content_async", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await provider.check_grammar("The cat sat on the mat.")

    assert result.has_issues is False
```

**Step 2: Run test to verify new tests fail**

Run: `cd backend && python -m pytest tests/test_providers.py -v`
Expected: FAIL — imports fail for openai/gemini providers

**Step 3: Write OpenAI provider**

Create `backend/providers/openai.py`:

```python
import json

import openai

from providers import GrammarResult

SYSTEM_PROMPT = (
    "Check the grammar of the following text. Explain issues if you find. "
    'Respond with JSON: {"has_issues": true/false, "explanation": "markdown text"}'
)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        return GrammarResult(
            has_issues=data["has_issues"],
            explanation=data.get("explanation", ""),
        )
```

**Step 4: Write Gemini provider**

Create `backend/providers/gemini.py`:

```python
import json

from google import genai

from providers import GrammarResult

SYSTEM_PROMPT = (
    "Check the grammar of the following text. Explain issues if you find. "
    'Respond with JSON: {"has_issues": true/false, "explanation": "markdown text"}'
)


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.models.generate_content_async(
            model=self._model,
            contents=text,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        data = json.loads(response.text)
        return GrammarResult(
            has_issues=data["has_issues"],
            explanation=data.get("explanation", ""),
        )
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_providers.py -v`
Expected: PASS (all 5 tests)

**Step 6: Commit**

```bash
git add backend/providers/ backend/tests/test_providers.py
git commit -m "feat: add OpenAI and Gemini providers"
```

---

### Task 6: Provider Factory

**Files:**
- Modify: `backend/providers/__init__.py`
- Modify: `backend/tests/test_providers.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_providers.py`:

```python
from providers import create_provider


def test_create_anthropic_provider():
    p = create_provider("anthropic", "claude-sonnet-4-5-20250929", anthropic_api_key="key")
    assert isinstance(p, AnthropicProvider)


def test_create_openai_provider():
    p = create_provider("openai", "gpt-4o", openai_api_key="key")
    assert isinstance(p, OpenAIProvider)


def test_create_gemini_provider():
    p = create_provider("gemini", "gemini-2.0-flash", gemini_api_key="key")
    assert isinstance(p, GeminiProvider)


def test_create_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("unknown", "model")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_providers.py::test_create_anthropic_provider -v`
Expected: FAIL — `create_provider` not found

**Step 3: Write factory function**

Add to `backend/providers/__init__.py`:

```python
def create_provider(
    provider: str,
    model: str,
    *,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    gemini_api_key: str = "",
) -> GrammarProvider:
    match provider:
        case "anthropic":
            from providers.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=anthropic_api_key, model=model)
        case "openai":
            from providers.openai import OpenAIProvider
            return OpenAIProvider(api_key=openai_api_key, model=model)
        case "gemini":
            from providers.gemini import GeminiProvider
            return GeminiProvider(api_key=gemini_api_key, model=model)
        case _:
            raise ValueError(f"Unknown provider: {provider}")
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_providers.py -v`
Expected: PASS (all 9 tests)

**Step 5: Commit**

```bash
git add backend/providers/__init__.py backend/tests/test_providers.py
git commit -m "feat: add provider factory function"
```

---

### Task 7: In-Memory Store and WebSocket Manager

**Files:**
- Create: `backend/store.py`
- Create: `backend/tests/test_store.py`

**Step 1: Write the failing test**

Create `backend/tests/test_store.py`:

```python
import asyncio
from unittest.mock import AsyncMock

import pytest

from store import CheckResult, ResultStore


@pytest.fixture
def store():
    return ResultStore()


def test_add_result(store):
    result = CheckResult(
        username="alice",
        prompt="He go to store",
        has_issues=True,
        explanation="Grammar issue.",
    )
    store.add(result)
    assert len(store.results) == 1
    assert store.results[0].username == "alice"
    assert store.results[0].timestamp is not None


@pytest.mark.asyncio
async def test_websocket_broadcast(store):
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    store.connect(ws1)
    store.connect(ws2)

    result = CheckResult(
        username="bob",
        prompt="Test",
        has_issues=False,
        explanation="No issues.",
    )
    await store.add_and_broadcast(result)

    assert ws1.send_json.call_count == 1
    assert ws2.send_json.call_count == 1
    sent = ws1.send_json.call_args[0][0]
    assert sent["username"] == "bob"


@pytest.mark.asyncio
async def test_disconnect_removes_ws(store):
    ws = AsyncMock()
    store.connect(ws)
    store.disconnect(ws)

    result = CheckResult(username="x", prompt="y", has_issues=False, explanation="")
    await store.add_and_broadcast(result)

    ws.send_json.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: FAIL — `store` module not found

**Step 3: Write implementation**

Create `backend/store.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CheckResult:
    username: str
    prompt: str
    has_issues: bool
    explanation: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "prompt": self.prompt,
            "has_issues": self.has_issues,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }


class ResultStore:
    def __init__(self):
        self.results: list[CheckResult] = []
        self._connections: list = []

    def add(self, result: CheckResult):
        self.results.append(result)

    def connect(self, websocket):
        self._connections.append(websocket)

    def disconnect(self, websocket):
        self._connections.remove(websocket)

    async def add_and_broadcast(self, result: CheckResult):
        self.add(result)
        data = result.to_dict()
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/store.py backend/tests/test_store.py
git commit -m "feat: add in-memory result store with WebSocket broadcast"
```

---

### Task 8: FastAPI App — `/api/check` Endpoint and WebSocket

**Files:**
- Modify: `backend/main.py`
- Create: `backend/tests/test_check.py`

**Step 1: Write the failing test**

Create `backend/tests/test_check.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from main import app, store, auth


@pytest.fixture(autouse=True)
def reset_store():
    store.results.clear()
    store._connections.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_check_returns_202(client):
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.post(
            "/api/check",
            json={"prompt": "He go to store"},
            headers={"Authorization": "Bearer tok_test"},
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_check_invalid_token(client):
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

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_check.py -v`
Expected: FAIL — imports/attributes missing

**Step 3: Write the full `backend/main.py`**

```python
import asyncio

from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from auth import TokenAuth
from config import Settings
from providers import create_provider
from store import CheckResult, ResultStore

settings = Settings()
app = FastAPI(title="Hoshi")
store = ResultStore()
auth = TokenAuth(settings.tokens_file)
provider = create_provider(
    settings.provider,
    settings.model,
    anthropic_api_key=settings.anthropic_api_key,
    openai_api_key=settings.openai_api_key,
    gemini_api_key=settings.gemini_api_key,
)


class CheckRequest(BaseModel):
    prompt: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/check", status_code=202)
async def check(
    body: CheckRequest,
    authorization: str = Header(default=""),
):
    token = authorization.removeprefix("Bearer ").strip()
    username = auth.validate(token)
    if not username:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    asyncio.create_task(_run_check(username, body.prompt))
    return {"status": "accepted"}


async def _run_check(username: str, prompt: str):
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
        )
        await store.add_and_broadcast(error_result)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    store.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        store.disconnect(websocket)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_check.py tests/test_health.py -v`
Expected: PASS

Note: the test for `test_check_returns_202` patches `auth.validate` so token auth passes, and the `_run_check` background task will fail silently (no real LLM). That's fine — we only test the HTTP layer here.

**Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_check.py
git commit -m "feat: add /api/check endpoint with async grammar checking and WebSocket"
```

---

### Task 9: Frontend — Dashboard HTML/JS/CSS

**Files:**
- Create: `frontend/static/index.html`
- Create: `frontend/static/app.js`
- Create: `frontend/static/style.css`

**Step 1: Write `frontend/static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hoshi — Grammar Dashboard</title>
    <link rel="stylesheet" href="style.css">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
    <header>
        <h1>Hoshi</h1>
        <span id="status" class="status disconnected">disconnected</span>
    </header>
    <main id="feed"></main>
    <script src="app.js"></script>
</body>
</html>
```

**Step 2: Write `frontend/static/style.css`**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    background: #0d1117;
    color: #c9d1d9;
    max-width: 800px;
    margin: 0 auto;
    padding: 1rem;
}

header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 0;
    border-bottom: 1px solid #21262d;
    margin-bottom: 1rem;
}

h1 { font-size: 1.5rem; color: #f0f6fc; }

.status {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
}
.status.connected { background: #238636; color: #fff; }
.status.disconnected { background: #da3633; color: #fff; }

.entry {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 0.75rem;
}

.entry-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
    color: #8b949e;
}

.badge {
    font-size: 0.7rem;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
    font-weight: 600;
}
.badge.clean { background: #238636; color: #fff; }
.badge.issues { background: #da3633; color: #fff; }

.prompt {
    background: #0d1117;
    padding: 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
    white-space: pre-wrap;
    word-break: break-word;
    cursor: pointer;
    max-height: 4.5em;
    overflow: hidden;
}
.prompt.expanded { max-height: none; }

.explanation {
    font-size: 0.9rem;
    line-height: 1.5;
    padding-top: 0.5rem;
    border-top: 1px solid #21262d;
}
.explanation p { margin-bottom: 0.5rem; }
.explanation code {
    background: #0d1117;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    font-size: 0.85em;
}
```

**Step 3: Write `frontend/static/app.js`**

```javascript
const feed = document.getElementById("feed");
const status = document.getElementById("status");

function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        status.textContent = "connected";
        status.className = "status connected";
    };

    ws.onclose = () => {
        status.textContent = "disconnected";
        status.className = "status disconnected";
        setTimeout(connect, 3000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        addEntry(data);
    };
}

function addEntry(data) {
    const entry = document.createElement("div");
    entry.className = "entry";

    const time = new Date(data.timestamp).toLocaleString();
    const badgeClass = data.has_issues ? "issues" : "clean";
    const badgeText = data.has_issues ? "issues found" : "clean";

    entry.innerHTML = `
        <div class="entry-header">
            <strong>${escapeHtml(data.username)}</strong>
            <span>${time}</span>
            <span class="badge ${badgeClass}">${badgeText}</span>
        </div>
        <div class="prompt" onclick="this.classList.toggle('expanded')">${escapeHtml(data.prompt)}</div>
        ${data.has_issues ? `<div class="explanation">${marked.parse(data.explanation)}</div>` : ""}
    `;

    feed.prepend(entry);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

connect();
```

**Step 4: Verify files exist**

```bash
ls frontend/static/
```
Expected: `app.js  index.html  style.css`

**Step 5: Commit**

```bash
git add frontend/static/
git commit -m "feat: add dashboard frontend with real-time WebSocket feed"
```

---

### Task 10: Nginx Configuration

**Files:**
- Create: `frontend/nginx.conf`

**Step 1: Write `frontend/nginx.conf`**

```nginx
server {
    listen 80;

    auth_basic "Hoshi Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        root /usr/share/nginx/html;
        index index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

**Step 2: Commit**

```bash
git add frontend/nginx.conf
git commit -m "feat: add nginx config with basic auth and WebSocket proxy"
```

---

### Task 11: Dockerfiles

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`

**Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Write `frontend/Dockerfile`**

```dockerfile
FROM nginx:alpine

ARG DASHBOARD_USER=admin
ARG DASHBOARD_PASSWORD=changeme

RUN apk add --no-cache apache2-utils && \
    htpasswd -cb /etc/nginx/.htpasswd "$DASHBOARD_USER" "$DASHBOARD_PASSWORD"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY static/ /usr/share/nginx/html/
```

**Step 3: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile
git commit -m "feat: add Dockerfiles for backend and frontend"
```

---

### Task 12: Docker Compose and Example Files

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `tokens.json.example`

**Step 1: Write `docker-compose.yml`**

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
    build:
      context: ./frontend
      args:
        DASHBOARD_USER: ${DASHBOARD_USER:-admin}
        DASHBOARD_PASSWORD: ${DASHBOARD_PASSWORD:-changeme}
    ports:
      - "8080:80"
    depends_on:
      - backend
```

**Step 2: Write `.env.example`**

```
PROVIDER=anthropic
MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AI...
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=changeme
```

**Step 3: Write `tokens.json.example`**

```json
{
  "tok_replace_with_real_token_1": "username1",
  "tok_replace_with_real_token_2": "username2"
}
```

**Step 4: Commit**

```bash
git add docker-compose.yml .env.example tokens.json.example
git commit -m "feat: add docker-compose and example config files"
```

---

### Task 13: Claude Code Hook Script

**Files:**
- Create: `hook/hook.sh`

**Step 1: Write `hook/hook.sh`**

```bash
#!/bin/bash
# Hoshi grammar check hook for Claude Code
# Env vars required: HOSHI_SERVER_URL, HOSHI_TOKEN

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt')

# Skip empty prompts
[ -z "$PROMPT" ] && exit 0

curl -s -X POST "$HOSHI_SERVER_URL/api/check" \
  -H "Authorization: Bearer $HOSHI_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": $(echo "$PROMPT" | jq -Rs .)}" \
  >/dev/null 2>&1 &
```

**Step 2: Make executable**

```bash
chmod +x hook/hook.sh
```

**Step 3: Commit**

```bash
git add hook/hook.sh
git commit -m "feat: add Claude Code hook script"
```

---

### Task 14: Integration Smoke Test with Docker Compose

**Files:**
- Create: `tests/test_integration.sh`

**Step 1: Write integration test script**

Create `tests/test_integration.sh`:

```bash
#!/bin/bash
# Smoke test: build, start, test health, test check, tear down
set -e

echo "=== Building containers ==="
docker compose build

echo "=== Starting containers ==="
docker compose up -d

echo "=== Waiting for backend ==="
for i in $(seq 1 30); do
    if curl -sf http://localhost:8080/api/health > /dev/null 2>&1; then
        echo "Backend is up"
        break
    fi
    sleep 1
done

echo "=== Testing health endpoint ==="
HEALTH=$(curl -sf -u admin:changeme http://localhost:8080/api/health)
echo "Health: $HEALTH"

echo "=== Testing check endpoint with invalid token ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u admin:changeme \
  -X POST http://localhost:8080/api/check \
  -H "Authorization: Bearer invalid" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}')
echo "Invalid token status: $STATUS (expected 401)"
[ "$STATUS" = "401" ] || { echo "FAIL"; exit 1; }

echo "=== Tearing down ==="
docker compose down

echo "=== ALL SMOKE TESTS PASSED ==="
```

**Step 2: Make executable and commit**

```bash
chmod +x tests/test_integration.sh
git add tests/test_integration.sh
git commit -m "test: add Docker Compose integration smoke test"
```

---

### Task 15: Add `.gitignore` and `.env` to prevent secret leaks

**Files:**
- Create: `.gitignore`

**Step 1: Write `.gitignore`**

```
.env
tokens.json
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Project scaffolding | - |
| 2 | Health endpoint test | 1 |
| 3 | Token auth | 3 |
| 4 | Anthropic provider | 2 |
| 5 | OpenAI + Gemini providers | 2 |
| 6 | Provider factory | 4 |
| 7 | Store + WebSocket manager | 3 |
| 8 | `/api/check` endpoint + WebSocket route | 3 |
| 9 | Frontend dashboard | - |
| 10 | Nginx config | - |
| 11 | Dockerfiles | - |
| 12 | Docker Compose + examples | - |
| 13 | Hook script | - |
| 14 | Integration smoke test | 1 script |
| 15 | `.gitignore` | - |

**Total: 15 tasks, ~18 unit tests, 1 integration script**
