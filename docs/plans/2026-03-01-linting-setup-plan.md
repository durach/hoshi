# Linting & Task Runner Setup — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ruff + mypy + taskipy linting toolchain to hoshi, mirroring the svarog02 project setup.

**Architecture:** Single `pyproject.toml` at project root holds all tool config and dev dependencies. Existing `requirements.txt` files stay for Docker. Local dev uses `uv` with taskipy tasks.

**Tech Stack:** ruff (linter + formatter), mypy (type checker), taskipy (task runner), uv (package manager)

---

### Task 1: Create pyproject.toml

**Files:**
- Create: `pyproject.toml`

**Step 1: Create the pyproject.toml file**

Create `pyproject.toml` at project root with this exact content:

```toml
[project]
name = "hoshi"
version = "0.1.0"
description = "Grammar teaching tool for Claude Code"
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.115.0,<1.0",
    "uvicorn[standard]>=0.34.0,<1.0",
    "anthropic>=0.52.0,<1.0",
    "openai>=1.82.0,<2.0",
    "google-genai>=1.14.0,<2.0",
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-asyncio>=0.25.0,<1.0",
    "httpx>=0.28.0,<1.0",
    "ruff>=0.11.0",
    "mypy>=1.13.0",
    "taskipy>=1.12.0",
]

# =============================================================================
# Ruff Configuration
# =============================================================================
[tool.ruff]
line-length = 88
target-version = "py312"
src = ["backend"]

include = ["*.py", "*.pyi"]

exclude = [
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
]

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # Pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
    "TCH",    # flake8-type-checking
    "PTH",    # flake8-use-pathlib
    "ERA",    # eradicate (commented-out code)
    "PL",     # Pylint
    "RUF",    # Ruff-specific rules
    "ASYNC",  # flake8-async
    "S",      # flake8-bandit (security)
]

ignore = [
    "E501",    # Line too long (handled by formatter)
    "PLC0415", # Import not at top level
    "PLR0913", # Too many arguments
    "PLR2004", # Magic value comparison
    "S101",    # Use of assert (global ignore for tests convenience)
]

fixable = ["ALL"]
unfixable = []

[tool.ruff.lint.per-file-ignores]
"backend/tests/**/*.py" = ["S101", "PLR2004", "ARG001"]

[tool.ruff.lint.isort]
force-single-line = false
lines-after-imports = 2

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"

# =============================================================================
# Mypy Configuration
# =============================================================================
[tool.mypy]
python_version = "3.12"
strict = false
warn_return_any = true
warn_unused_ignores = true
check_untyped_defs = true
show_error_codes = true
show_column_numbers = true
pretty = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
disallow_incomplete_defs = false

[[tool.mypy.overrides]]
module = [
    "anthropic.*",
    "openai.*",
    "google.*",
    "google.genai.*",
]
ignore_missing_imports = true

# =============================================================================
# Pytest Configuration
# =============================================================================
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "strict"

addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
]

filterwarnings = [
    "error",
    "ignore::DeprecationWarning",
    "ignore::ResourceWarning",
]

# =============================================================================
# Taskipy Configuration
# =============================================================================
[tool.taskipy.tasks]
lint = "ruff check backend/"
typecheck = "mypy backend/"
test = "cd backend && pytest -v"
fix = "ruff check backend/ --fix"
format = "ruff format backend/"
check = "task lint && task typecheck && task test"
```

**Step 2: Verify pyproject.toml is valid**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb')); print('valid')"`
Expected: `valid`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pyproject.toml with ruff, mypy, and taskipy config"
```

---

### Task 2: Install dev dependencies

**Step 1: Install the project with dev extras using uv**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && uv pip install -e ".[dev]"`

**Step 2: Verify tools are available**

Run these three commands:
```bash
ruff version
mypy --version
task --version
```

Expected: version output for each (no "command not found").

**Step 3: No commit needed** (venv changes are gitignored)

---

### Task 3: Run ruff and fix issues

**Step 1: Run ruff check to see current violations**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && ruff check backend/`

Note: there will likely be violations. Record them.

**Step 2: Auto-fix safe violations**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && ruff check backend/ --fix`

**Step 3: Run ruff format to fix formatting**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && ruff format backend/`

**Step 4: Run ruff check again to see remaining violations**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && ruff check backend/`

If there are remaining violations that can't be auto-fixed, fix them manually. Common ones:
- Unused imports: remove them
- Security warnings (S-rules): add `# noqa: S...` if they're false positives, or fix the actual issue
- Unused arguments in non-test code: prefix with `_` or remove

**Step 5: Verify all tests still pass**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && cd backend && python -m pytest -v`
Expected: all 29 tests pass.

**Step 6: Commit**

```bash
git add -A
git commit -m "style: fix ruff lint and format violations"
```

---

### Task 4: Run mypy and fix issues

**Step 1: Run mypy to see current type errors**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && mypy backend/`

Note: with `strict = false` and `check_untyped_defs = true`, expect mostly:
- Missing imports for third-party libraries (should be handled by overrides)
- Possible type errors in actual code

**Step 2: Fix any real type errors**

Fix genuine type errors found by mypy. Do NOT add `# type: ignore` unless the error is a false positive. If a third-party module is missing stubs and isn't covered by the overrides, add it to the `[[tool.mypy.overrides]]` section in pyproject.toml.

**Step 3: Verify all tests still pass**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && cd backend && python -m pytest -v`
Expected: all 29 tests pass.

**Step 4: Commit**

```bash
git add -A
git commit -m "fix: resolve mypy type errors"
```

---

### Task 5: Verify taskipy tasks work end-to-end

**Step 1: Run the full check task**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && uv run task check`

Expected: lint passes, typecheck passes, all tests pass. Zero exit code.

**Step 2: Verify individual tasks work**

Run each:
```bash
uv run task lint
uv run task typecheck
uv run task test
uv run task fix
uv run task format
```

All should exit 0.

**Step 3: No commit needed** (no file changes)

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update the development instructions**

Replace the "Local setup" and "Running tests" sections with:

```markdown
### Local setup
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Running checks
```bash
uv run task check    # lint + typecheck + tests (all at once)
uv run task lint     # ruff linter only
uv run task typecheck # mypy only
uv run task test     # pytest only
uv run task fix      # auto-fix lint issues
uv run task format   # auto-format code
```
```

Keep the note about tests mocking SDK constructors.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with taskipy commands"
```

---

### Task 7: Add uv.lock and update .gitignore

**Step 1: Generate uv.lock**

Run: `cd /Users/dmytro/Projects/grammar/hoshi && uv lock`

This creates a `uv.lock` file for reproducible installs.

**Step 2: Commit**

```bash
git add uv.lock
git commit -m "build: add uv.lock for reproducible installs"
```
