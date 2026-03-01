# Review Fixes Design — 2026-03-01

Fixes all 13 findings from the CC code review and Codex review report.

## Security

### 1. XSS via marked.parse
- **File:** `frontend/static/app.js:40`
- **Fix:** Add DOMPurify. Sanitize before innerHTML: `DOMPurify.sanitize(marked.parse(data.explanation))`.
- **Changes:** Add DOMPurify script tag to `index.html`, one-line change in `app.js`.

### 2. WebSocket authentication
- **Files:** `backend/main.py`, `frontend/static/app.js`, `frontend/nginx.conf`, `frontend/index.html`
- **Fix:** Backend `/ws` endpoint accepts `token` query param, validates via `TokenAuth` before `accept()`. Closes with code 4401 if invalid.
- **Token delivery:** Frontend gets token from a `<meta name="ws-token">` tag. The tag contains a placeholder `__WS_TOKEN__` that is replaced at container startup via `envsubst` in the entrypoint script.
- **Config:** `WS_TOKEN` env var in `docker-compose.yml`, must match a token in `tokens.json`.

### 3. Dashboard password out of image layer
- **File:** `frontend/Dockerfile`
- **Fix:** Remove `ARG DASHBOARD_PASSWORD` and build-time `htpasswd` from Dockerfile. Add an entrypoint script (`entrypoint.sh`) that:
  1. Generates `.htpasswd` from `DASHBOARD_USER` / `DASHBOARD_PASSWORD` env vars.
  2. Runs `envsubst` to inject `WS_TOKEN` into `index.html` from a template.
  3. Execs `nginx -g 'daemon off;'`.
- **Config:** `DASHBOARD_USER`, `DASHBOARD_PASSWORD`, `WS_TOKEN` as runtime env vars.

## Bugs

### 4. Task GC
- **File:** `backend/main.py`
- **Fix:** Add `_background_tasks: set[asyncio.Task]` at module level (later: on `app.state` after #9). Store task refs, discard via `add_done_callback`.

### 5. JSON parse handling
- **Files:** `backend/providers/anthropic.py`, `openai.py`, `gemini.py`
- **Fix:** Before `json.loads`, strip markdown fences (` ```json ... ``` `). Wrap in try/except `JSONDecodeError`, raise `ValueError("Provider returned invalid JSON")`.

### 6. Disconnect ValueError
- **File:** `backend/store.py`
- **Fix:** Change `_connections` from `list` to `set`. Use `add()` / `discard()` everywhere.

### 7. Error results as clean
- **Files:** `backend/store.py`, `backend/main.py`, `frontend/static/app.js`, `frontend/static/style.css`
- **Fix:** Add `status` field to `CheckResult` — values: `"clean"`, `"issues"`, `"error"`. Default derived from `has_issues` in `__post_init__`. Error path in `_run_check` sets `status="error"`.
- **Frontend:** Badge logic uses `data.status`. New `.badge.error` CSS class (orange/red).

## Code Smells

### 8. Duplicated SYSTEM_PROMPT
- **Files:** `backend/providers/__init__.py`, `anthropic.py`, `openai.py`, `gemini.py`
- **Fix:** Move `SYSTEM_PROMPT` to `providers/__init__.py`. Import in each provider.

### 9. Module-level side effects
- **Files:** `backend/main.py`, `backend/tests/conftest.py`, `backend/tests/test_check.py`
- **Fix:** Wrap initialization in a FastAPI lifespan context manager. Settings, auth, store, provider become `app.state` attributes. Route handlers access via `request.app.state`. Tests create the app with test config directly.

### 10. Test deps in production requirements
- **Files:** `backend/requirements.txt`, new `backend/requirements-dev.txt`
- **Fix:** Move `pytest`, `pytest-asyncio`, `httpx` to `requirements-dev.txt`. Production image only installs `requirements.txt`.

### 11. Duplicate client fixture
- **Files:** `backend/tests/conftest.py`, `backend/tests/test_check.py`
- **Fix:** Remove `client` fixture from `test_check.py`. Refactor `conftest.py` to expose `store` and `auth` as separate fixtures.

## Minor

### 12. Unbounded in-memory storage
- **File:** `backend/store.py`
- **Fix:** Cap `results` at 1000 entries. Trim oldest in `add()`.

### 13. HTTPException instead of JSONResponse
- **File:** `backend/main.py`
- **Fix:** Replace `return JSONResponse(status_code=401, ...)` with `raise HTTPException(status_code=401, detail="unauthorized")`.
