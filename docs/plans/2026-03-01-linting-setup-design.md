# Linting & Task Runner Setup — Design

## Decision
Mirror the svarog02 project toolchain: **ruff + mypy + taskipy**, configured in a new `pyproject.toml`.

## Scope
- Backend Python code only (frontend is 55 lines of vanilla JS — skipped)
- Local development only (Docker builds unchanged)

## Components

### 1. pyproject.toml (new file at project root)
Non-package project (no build-system, no entry points). Contains:
- `[project]` metadata + dependencies (mirrors current `requirements.txt`)
- `[project.optional-dependencies] dev` (mirrors `requirements-dev.txt` + adds ruff, mypy, taskipy)
- `[tool.ruff]` config
- `[tool.mypy]` config
- `[tool.pytest.ini_options]` config
- `[tool.taskipy.tasks]` task definitions

### 2. Ruff config
Adapted from svarog02:
- `line-length = 88`, `target-version = "py312"`
- `src = ["backend"]`
- Rule set: `E, W, F, I, B, C4, UP, ARG, SIM, TCH, PTH, ERA, PL, RUF, ASYNC, S`
- Per-file ignores for `backend/tests/`

### 3. Mypy config (gradual adoption)
Unlike svarog02's `strict = true`, hoshi starts lenient since the codebase is currently untyped:
- `strict = false`
- Key checks enabled: `warn_return_any`, `check_untyped_defs`, `show_error_codes`
- `disallow_untyped_defs = false` (no immediate annotation requirement)
- `ignore_missing_imports` for third-party modules (anthropic, openai, google-genai)

### 4. Taskipy tasks
```
lint      = "ruff check backend/"
typecheck = "mypy backend/"
test      = "cd backend && pytest -v"
fix       = "ruff check backend/ --fix"
format    = "ruff format backend/"
check     = "task lint && task typecheck && task test"
```

Usage: `uv run task check` (or individual tasks)

### 5. Dependency strategy
- `requirements.txt` and `requirements-dev.txt` kept as-is for Docker
- `pyproject.toml` is the source of truth for local dev with `uv`
- Slight duplication accepted to avoid Docker changes

### 6. CLAUDE.md update
Update dev instructions to reference `uv run task check`.

## What's NOT included
- Frontend linting (too small to justify tooling)
- Pre-commit hooks (can be added later)
- CI/CD integration (no CI exists yet)
- Docker build changes
