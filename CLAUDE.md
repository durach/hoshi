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
- nginx basic auth protects `/` only; `/api/` and `/ws` use bearer token auth
- Backend loads `tokens.json` at startup — restart after changes
- All tests run from `backend/` directory
