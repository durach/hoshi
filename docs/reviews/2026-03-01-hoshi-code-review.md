# Hoshi Code Review — 2026-03-01

Status: **Closed** — all 13 findings fixed in commits `92039ae..3b8baad`.

Full codebase review covering security, correctness, and code smells.

## Security

### 1. XSS via LLM explanation

**File:** `frontend/static/app.js:38`

```js
${data.has_issues ? `<div class="explanation">${marked.parse(data.explanation)}</div>` : ""}
```

The explanation originates from an LLM and is rendered as raw HTML via `marked.parse()`. The `marked` library does not sanitize HTML by default. If the LLM returns `<script>` tags or event handlers in the explanation, they execute in the browser.

**Fix:** Use `marked` with a sanitizer (e.g. DOMPurify), or use `marked`'s built-in hooks to strip dangerous HTML.

### 2. WebSocket has no authentication

**File:** `backend/main.py:68-74`

The `/ws` endpoint accepts all connections without any token check. Anyone who discovers the URL can see every user's prompts and grammar results in real time. The `/api/check` endpoint validates bearer tokens, but `/ws` does not.

**Fix:** Accept a token as a query parameter or in the first message, validate it with `TokenAuth` before accepting the connection.

### 3. Dashboard password baked into image layer

**File:** `frontend/Dockerfile:3-6`

`DASHBOARD_PASSWORD` is a build arg written into an image layer via `htpasswd`. Anyone with access to the image can extract it from the layer history (`docker history`).

**Fix:** Generate `.htpasswd` at runtime via an entrypoint script that reads from environment variables.

## Bugs / Correctness

### 4. `asyncio.create_task` without holding a reference

**File:** `backend/main.py:48`

```python
asyncio.create_task(_run_check(username, body.prompt))
```

Per Python docs, the event loop only holds a weak reference to tasks. The task can be garbage-collected mid-execution.

**Fix:**

```python
_background_tasks = set()

task = asyncio.create_task(_run_check(...))
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

### 5. No JSON parse error handling in providers

**Files:** `backend/providers/anthropic.py`, `openai.py`, `gemini.py`

Every provider does `json.loads(response...)` with no guard. LLMs frequently return non-JSON (markdown fences, preamble text, etc.). This raises `JSONDecodeError`, caught by the generic `except Exception` in `_run_check`, but the user gets a cryptic error message with no indication it was a parse issue.

**Fix:** Wrap `json.loads` in a try/except and return a clear error, or strip markdown fences before parsing.

### 6. `disconnect` can raise `ValueError`

**File:** `backend/store.py:39`

```python
def disconnect(self, websocket):
    self._connections.remove(websocket)
```

If called twice for the same websocket (race condition or duplicate disconnect event), `.remove()` raises `ValueError`.

**Fix:** Use a set instead of a list for `_connections` and call `discard()`, or guard with `if websocket in self._connections`.

### 7. Error results marked as `has_issues=False`

**File:** `backend/main.py:60-65`

When `_run_check` fails, it broadcasts a result with `has_issues=False`. The dashboard shows this as "clean" with a green badge, even though the check actually failed. The frontend cannot distinguish "no grammar issues" from "provider crashed".

**Fix:** Add an `error` field to `CheckResult`, or use a distinct status value. Render errors differently on the dashboard.

## Code Smells

### 8. Duplicated `SYSTEM_PROMPT` across all three providers

**Files:** `backend/providers/anthropic.py:7-9`, `openai.py:7-9`, `gemini.py:7-9`

The exact same prompt string is copy-pasted in all three provider files. If the prompt is tweaked, it must be changed in three places.

**Fix:** Move `SYSTEM_PROMPT` to `providers/__init__.py` and import it.

### 9. Module-level side effects in `main.py`

**File:** `backend/main.py:12-22`

Settings, auth, store, and provider are all instantiated at import time. This forces tests into awkward gymnastics — `conftest.py` must patch SDK constructors before importing `main`. It also makes it impossible to run the app with different configurations without reloading the module.

**Fix:** Use a factory function or FastAPI's lifespan events to initialize dependencies.

### 10. Test dependencies in production `requirements.txt`

**File:** `backend/requirements.txt:8-10`

`pytest`, `pytest-asyncio`, and `httpx` are bundled with production dependencies. The Docker image installs them unnecessarily, increasing image size and attack surface.

**Fix:** Split into `requirements.txt` (production) and `requirements-dev.txt` (test/dev).

### 11. Duplicate client fixture

**File:** `backend/tests/test_check.py:10-17`

`test_check.py` defines its own `client` fixture (returning a tuple of `(client, store, auth)`) that shadows the `conftest.py` `client` fixture. Meanwhile `test_health.py` uses the conftest one. The same fixture name means different things in different test files.

**Fix:** Rename the `test_check.py` fixture to something distinct (e.g. `client_with_deps`), or refactor conftest to expose `store` and `auth` as separate fixtures.

## Minor

### 12. Unbounded in-memory storage

**File:** `backend/store.py:29`

`self.results` grows without limit. For a small-scale tool this is acceptable, but long-running instances will slowly leak memory.

**Fix:** Cap results at a maximum (e.g. 1000) and evict oldest entries.

### 13. Manual 401 instead of `HTTPException`

**File:** `backend/main.py:46`

```python
return JSONResponse(status_code=401, content={"error": "unauthorized"})
```

This bypasses FastAPI's exception handling and middleware. Using `raise HTTPException(status_code=401, detail="unauthorized")` is more idiomatic and ensures middleware (e.g. CORS, logging) processes the error response consistently.

## Summary

| Severity   | # | Items |
|------------|---|-------|
| Security   | 3 | XSS via marked, unauthenticated WebSocket, password in image layer |
| Bug        | 4 | GC'd tasks, JSON parse failures, disconnect ValueError, misleading error results |
| Code smell | 4 | Duplicated prompt, module-level side effects, mixed deps, duplicate fixture |
| Minor      | 2 | Unbounded store, non-idiomatic error response |

### Recommended priority

1. **XSS via marked** — straightforward fix, real attack vector
2. **WebSocket auth** — exposes all user prompts to unauthenticated viewers
3. **Task GC** — silent data loss in production
4. **JSON parse handling** — most common runtime failure mode with LLMs
