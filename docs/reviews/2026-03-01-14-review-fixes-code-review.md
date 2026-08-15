# Code Review Report

Date: 2026-03-01
Scope: Full diff of 12 commits fixing all 13 findings from CC code review and Codex review report
Base: 8452be1 / Head: ca1e116

## Status
**Closed** — all findings fixed in commit `3b8baad`.

## Decision
Approve with minor comments.

## Findings

### P1 - Replace WS token placeholder with envsubst syntax
- File: `frontend/static/index.html:6`
- Issue: Template uses `__WS_TOKEN__`, but `entrypoint.sh` runs `envsubst '${WS_TOKEN}'`, which only substitutes `$WS_TOKEN` or `${WS_TOKEN}`.
- Impact: Token is never injected. WebSocket auth fails at runtime in Docker.
- Required fix: Change `__WS_TOKEN__` to `${WS_TOKEN}` in the template.
- Note: Also flagged independently in `2026-03-01-13-12-codex-ws-token-template-review.md`.

### P2 - No WebSocket authentication tests
- Files: `backend/tests/test_check.py`, `backend/tests/conftest.py`
- Issue: WebSocket endpoint now requires token auth but has zero test coverage.
- Impact: Auth regressions in `/ws` would go undetected.
- Required fix: Add tests for rejected (no token / bad token) and accepted (valid token) WebSocket connections.

### P2 - WebSocket reconnect loops forever on auth failure
- File: `frontend/static/app.js:14-17`
- Issue: `onclose` handler unconditionally retries every 3 seconds. If token is missing or invalid, this creates an infinite retry loop.
- Impact: Browser hammers the server with doomed connection attempts. No user-visible feedback about the cause.
- Required fix: Check `event.code` and stop retrying on 4401.

### P3 - `_background_tasks` still module-level after lifespan refactor
- File: `backend/main.py:12`
- Issue: The lifespan refactor moved `store`, `auth`, `provider` to `app.state`, but `_background_tasks` was left as a module-level global.
- Impact: Inconsistent with refactoring goals. Works fine in practice for single-instance app.
- Suggested fix: Move to `app.state.background_tasks` inside the lifespan.

### P3 - Unused `field` import in store.py
- File: `backend/store.py:1`
- Issue: `from dataclasses import dataclass, field` — `field` is never used.
- Impact: Dead import. Pre-existing but touched in this diff.
- Suggested fix: Remove `field` from the import.

## Not Actionable (Noted)

- `websocket.close()` before `accept()` is ASGI-implementation-specific but works correctly with uvicorn/Starlette. Monitor if server changes.
- CDN scripts (`marked`, `dompurify`) have no version pins or SRI hashes. Pre-existing pattern for `marked`; `dompurify` added in this diff.
- `parse_provider_json` regex doesn't handle uppercase `JSON` fence tag. Sufficient for real-world LLM output.
- `test_store.py` defines a local `store` fixture that shadows the conftest one. Intentional (unit tests vs integration).

## Exit Criteria
- WS token placeholder uses envsubst-compatible syntax.
- WebSocket auth has test coverage for accept and reject paths.
- Frontend does not retry WebSocket on auth failure (code 4401).
