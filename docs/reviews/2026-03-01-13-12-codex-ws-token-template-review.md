# Codex Review Report

Date: 2026-03-01 13:12
Scope: Frontend runtime templating for WebSocket auth token in Docker flow

## Findings

### P1 - Replace WS token placeholder with envsubst syntax
- File: `frontend/static/index.html:6`
- Issue: The template uses `__WS_TOKEN__`, but `entrypoint.sh` runs `envsubst '${WS_TOKEN}'`, which only substitutes `$WS_TOKEN` or `${WS_TOKEN}`.
- Impact: In Docker runtime, the page keeps the literal `__WS_TOKEN__` value. WebSocket authentication fails with unauthorized errors when WS auth is enabled.
- Required fix: Replace `__WS_TOKEN__` with `${WS_TOKEN}` in the template so runtime injection works.

## Status
**Closed** — fixed in commit `3b8baad`. Placeholder changed to `${WS_TOKEN}`.
