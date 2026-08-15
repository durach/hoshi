# Hoshi Review Report

Date: 2026-03-01
Scope: Review findings provided in the latest patch review

## Status
**Closed** — all exit criteria met in commits `92039ae..3b8baad`.

## Decision
Do not approve this patch in its current state.

## Findings

### P1 - Require authentication on websocket dashboard feed
- File: `frontend/nginx.conf:19`
- Issue: `/ws` explicitly disables `auth_basic`.
- Risk: Unauthenticated users can subscribe to live prompts and explanations.
- Required fix: Enforce the same dashboard authentication policy for `/ws`.

### P1 - Sanitize rendered markdown before injecting into DOM
- File: `frontend/static/app.js:40`
- Issue: `marked.parse(data.explanation)` is injected via `innerHTML` without sanitization.
- Risk: Model output can execute arbitrary script in viewers' browsers (XSS).
- Required fix: Sanitize HTML (e.g. DOMPurify) before `innerHTML`, or render as plain text.

### P2 - Avoid marking failed checks as clean results
- File: `backend/main.py:62`
- Issue: Failure fallback sets `has_issues=False`.
- Risk: Provider/API failures appear as grammatically clean results.
- Required fix: Return explicit error state and render it distinctly from successful checks.

### P2 - Guard websocket disconnect against double removal
- File: `backend/store.py:39`
- Issue: `disconnect` calls `list.remove` unconditionally.
- Risk: Duplicate disconnect/removal paths raise `ValueError` during normal flows.
- Required fix: Make disconnect idempotent (membership guard or `set.discard`).

## Exit Criteria
- `/ws` requires auth equivalent to dashboard routes.
- Dashboard explanation rendering is XSS-safe.
- Error results are not classified as clean checks.
- Websocket disconnect path is idempotent and exception-safe.
