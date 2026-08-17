# CLAUDE.md

## Project
Hoshi — a grammar teaching tool for Claude Code. Checks prompt grammar via configurable LLM providers and displays results on a real-time web dashboard.

## Architecture
- Two Docker containers: FastAPI backend + nginx frontend
- Backend: Python 3.12, FastAPI, uvicorn
- Frontend: vanilla HTML/JS/CSS, WebSocket, marked.js
- LLM providers: Anthropic, OpenAI, Gemini (strategy pattern in `backend/providers/`)

## Development

### Local setup
```bash
uv venv .venv
source .venv/bin/activate
uv sync --extra dev
```

### Running checks
```bash
uv run task check      # lint + typecheck + tests (all at once)
uv run task lint       # ruff linter only
uv run task typecheck  # mypy only
uv run task test       # pytest only
uv run task fix        # auto-fix lint issues
uv run task format     # auto-format code
```

Tests mock SDK constructors to avoid SOCKS proxy issues. Use `pytest_asyncio.fixture` for async fixtures (strict mode).

The frontend has no build step and no test suite, so run `node --check
frontend/static/app.js` before committing — a syntax error there silently kills
the whole script, and the page still renders enough to look fine.

### Running the server
```bash
cp .env.example .env   # edit with real API key
cp tokens.json.example tokens.json  # edit with real tokens
docker compose up -d
```

Dashboard at `http://localhost:8080`.

### Key conventions
- Provider implementations follow the `GrammarProvider` protocol in `backend/providers/__init__.py`
- `tokens.json` format: `{"token_string": "username"}` (token is the key)
- Dashboard has no auth of its own; port 8080 is bound to loopback and fronted by
  a local Caddy host. `/api/` and `/ws` use bearer token auth
- The dashboard's HTML carries `WS_TOKEN` in a meta tag — keep the port on loopback
- Backend loads `tokens.json` at startup — restart after changes
- **`uv run task check` runs from the repo root**, not from `backend/` — the
  taskipy tasks are `ruff check backend/` and friends, so they resolve relative
  to the root and fail with a bare `E902` anywhere else. Only plain `pytest`
  runs from `backend/`
- `WS_TOKEN` must be set in `.env` and match a key in `tokens.json`, or the
  dashboard's WebSocket and `/api/results` both fail auth
- `checkers.json` follows the `tokens.json` pattern (gitignored, `.example` committed, loaded at startup, restart after changes). Exactly one `default: true` or the backend refuses to start. A missing file falls back to `PROVIDER`/`MODEL` from `.env`. Opinions live on the parent result and their debug records under `debug["opinions"]`, which stays off the WebSocket like all debug.

### How a check is shaped
- Providers do not return prose JSON. Each uses its own structured-output
  mechanism against `GRAMMAR_SCHEMA` — OpenAI strict `json_schema`, Anthropic a
  forced tool call, Gemini `response_schema` (which rejects
  `additionalProperties` at any depth, hence the recursive strip)
- The model returns `issues[{type, note}]` and `correction` only. `has_issues`
  and the header `types` are derived in `build_result`, so the model cannot
  contradict itself, and a lone `style` note never counts as a mistake
- `<mark data-type="...">` in the correction is no longer rendered. It is the
  input to `word_diff`, which pairs each change with the mark it falls inside
  and hands the dashboard `{op, before, after, type, sep}` segments. The entry
  shows removed text struck through and inserted text coloured by the issue it
  fixes; the client still validates the type against a known list before it
  becomes a class name
- `sep` carries the whitespace that followed each segment. Without it a renderer
  joining segments with single spaces swallows the line breaks, and a numbered
  list arrives as one run-on paragraph
- `diff` rides the normal broadcast payload — it is what the dashboard displays.
  Only `debug` is withheld
- Every check stores a `debug` record: the raw response, what `build_result`
  dropped, timing, and an analysis of which marked spans changed nothing.
  `analysis.py` is pure and knows no provider. It **observes only** — no verdict
  depends on it, because word alignment is a heuristic and suppressing a finding
  on a bad alignment would throw away a real correction
- `debug` is deliberately absent from `to_dict()`, so it never rides the
  WebSocket; only the derived `has_ghost_marks` bool does. Fetch a record from
  `/api/results/{id}/debug`
- Every colour in `style.css` is a token on `:root`, defined three times: the
  dark default, a `prefers-color-scheme: light` block for people who never
  touched the toggle, and a `[data-theme="light"]` block for those who did.
  A literal hex anywhere else is a bug in one theme — add the token instead.
  Tints come from `color-mix` with `--tint`, so a new accent needs one hue,
  not a background to match

### Gotchas
- Rebuilding or restarting the backend **clears the store** — expect an empty
  dashboard after `docker compose up --build`, and reseed before screenshotting
- Running the stack **from a worktree** needs two things. `.env` and
  `tokens.json` are gitignored, so they are absent there — symlink them from the
  main checkout rather than copying or, worse, printing them. And pass
  `-p hoshi` so compose reuses the existing project; without it the new one
  fights for `127.0.0.1:8080` and fails to start
- Result ids restart at 1 on every backend start, so each result carries a
  `run_id`; the dashboard resets its dedup state when that changes. Without it
  the page silently stops updating after a restart
- `hook/hook.sh` in the repo is the source, but the live copy is
  `~/.hoshi/hook.sh` — copy it across after editing or nothing changes
- The hook is registered globally in both `~/.claude/settings.json` and
  `~/.codex/config.toml`, so the dashboard shows prompts from every Claude Code
  and Codex session on the machine. Live traffic can appear mid-screenshot
- Codex sends the same `UserPromptSubmit` fields as Claude Code (`prompt`,
  `cwd`, `session_id`, `transcript_path`), which is why one script serves both.
  Which agent fired is therefore passed as the hook's first argument, not
  inferred — `hook.sh codex` vs `hook.sh claude-code`. It reaches the dashboard
  as a CSS class, so it is slug-checked in the hook, again in `CheckRequest`,
  and once more against `AGENT_LABELS` before it becomes one.
  Its rollout transcripts have no `queue-operation` entries, so the queue replay
  is a no-op there. Codex also trusts a hook by hash — edit the command in
  `config.toml` and it asks to be trusted again
- Prompts typed while Claude is working never fire `UserPromptSubmit`; the hook
  replays them from the transcript on its next run
- Models newer than `gpt-5.2` reject an explicit `temperature`
- **The repo is public and this project handles real prompts**, so treat any
  text copied from a live result as private until proven otherwise. The
  fixtures in `backend/tests/test_analysis.py` were captured verbatim once and
  had to be rewritten; they are synthetic now, and their wording is
  load-bearing — every marked span and corrected word is positioned to produce
  specific `difflib` opcodes, so rephrasing one breaks assertions that look
  unrelated
- `.githooks/pre-push` is the guard against that happening again. It needs
  `git config core.hooksPath .githooks` once per clone — a hook nobody enabled
  protects nothing, and nothing in git enables it for you. Private words live
  in `~/.hoshi/privacy-denylist.txt`, outside the repo. `bash
  tests/test-pre-push.sh` covers it, and asserts **exit codes**: two bugs
  during its development printed `BLOCKED` and then exited 0
- The guard's own fixtures have to look like leaks, so a `privacy-guard-allow`
  comment exempts the single line it sits on. Reach for it rather than
  `PRIVACY_GUARD=off`, which disables every check for the whole push. Neither
  the hook nor its tests may contain a real private term — the test denylist
  uses invented words on purpose
