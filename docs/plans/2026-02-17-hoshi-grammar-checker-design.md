# Hoshi — Grammar Teaching Tool for Claude Code

## Purpose

A teaching tool that checks grammar and spelling of Claude Code prompts and displays explanations on a real-time web dashboard. The goal is to help users learn better writing habits, not to correct text for them.

## Architecture

Approach C: separate nginx frontend + FastAPI backend, two Docker containers.

```
┌─────────────────┐         ┌─────────────────────────┐
│  Claude Code     │  POST   │  FastAPI Backend         │
│  Hook (bash/curl)│────────>│  /api/check              │
│  async, on user  │ Bearer  │                          │
│  machine         │ token   │  ┌─────────────────────┐ │
└─────────────────┘         │  │ LLM Provider         │ │
                            │  │ (anthropic/openai/   │ │
                            │  │  gemini)             │ │
                            │  └────────┬────────────┘ │
                            │           │              │
                            │  ┌────────v────────────┐ │
                            │  │ In-memory store      │ │
                            │  │ (list of results)    │ │
                            │  └────────┬────────────┘ │
                            │           │ WebSocket    │
                            │           │ broadcast    │
                            └───────────┼─────────────┘
                                        │
                            ┌───────────v─────────────┐
                            │  Nginx                   │
                            │  Serves static dashboard │
                            │  Proxies /api/* and      │
                            │  /ws to backend          │
                            └─────────────────────────┘
                                        │
                            ┌───────────v─────────────┐
                            │  Browser Dashboard       │
                            │  Vanilla JS + WebSocket  │
                            │  Chronological feed      │
                            └─────────────────────────┘
```

### Flow

1. User types a prompt in Claude Code.
2. `UserPromptSubmit` hook fires asynchronously, `curl`s the server with the prompt text + bearer token.
3. Server validates token, kicks off an async grammar check via the configured LLM provider.
4. Result is stored in memory and broadcast via WebSocket.
5. Dashboard receives the WebSocket message and appends it to the feed.

## Backend

### API Endpoints

- `POST /api/check` — receives prompt text + bearer token. Validates token, starts async grammar check. Returns `202 Accepted` immediately.
- `GET /api/health` — healthcheck for Docker.
- `WebSocket /ws` — broadcasts grammar check results to connected dashboards.

### LLM Provider Abstraction

Strategy pattern with a base protocol and three implementations:

- `AnthropicProvider` — uses `anthropic` SDK
- `OpenAIProvider` — uses `openai` SDK
- `GeminiProvider` — uses `google-genai` SDK

Selected at startup via `PROVIDER` and `MODEL` env vars. API key from provider-specific env var (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`).

### Grammar Check Prompt

```
Check the grammar of the following text. Explain issues if you find.
```

### Result Structure

```json
{
  "has_issues": true,
  "explanation": "Free-form markdown text from the LLM explaining any issues found."
}
```

The LLM has full freedom to explain however it wants. The dashboard renders the markdown as-is.

### Token Management

Tokens stored in `tokens.json` mounted as a Docker volume:

```json
{
  "tok_abc123": "dmytro",
  "tok_def456": "alice"
}
```

Validated on each `/api/check` request via `Authorization: Bearer <token>` header.

## Frontend

Single-page static site served by nginx.

- Connects to `/ws` WebSocket on load.
- Displays a chronological feed of grammar check results (newest at top).
- Each entry shows:
  - Timestamp
  - Username (from token lookup)
  - Original prompt text (truncated if long, expandable)
  - `has_issues` badge (green "clean" / red "issues found")
  - Rendered markdown explanation (if `has_issues` is true)
- Tech: vanilla HTML/JS/CSS + `marked.js` (CDN) for markdown rendering.
- Protected by nginx basic auth.

## Claude Code Hook

Bash script configured with `async: true` in the user's Claude Code settings:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.hoshi/hook.sh",
            "async": true
          }
        ]
      }
    ]
  }
}
```

`hook.sh`:

```bash
#!/bin/bash
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt')
curl -s -X POST "$HOSHI_SERVER_URL/api/check" \
  -H "Authorization: Bearer $HOSHI_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": $(echo "$PROMPT" | jq -Rs .)}" &
```

Env vars `HOSHI_SERVER_URL` and `HOSHI_TOKEN` set in the user's shell profile.

## Docker Setup

Two services via `docker-compose.yml`:

```yaml
services:
  backend:
    build: ./backend
    env_file: .env
    volumes:
      - ./tokens.json:/app/tokens.json:ro

  frontend:
    build: ./frontend
    ports:
      - "443:443"
    depends_on:
      - backend
```

### Environment Variables (`.env`)

```
PROVIDER=anthropic
MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_API_KEY=sk-...
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=...
```

## Project Structure

```
hoshi/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── gemini.py
│   └── config.py
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── hook/
│   └── hook.sh
├── docker-compose.yml
├── .env.example
└── tokens.json.example
```

## Key Decisions

- **Separate containers**: nginx frontend + FastAPI backend (Approach C)
- **Async hook**: fire-and-forget, never blocks Claude Code
- **Configurable LLM**: provider + model at startup (Anthropic/OpenAI/Gemini)
- **Simple result**: boolean + free-form markdown explanation
- **Auth**: bearer tokens for API, nginx basic auth for dashboard
- **Ephemeral**: in-memory store, no persistence across restarts
- **Real-time**: WebSocket broadcast to dashboard
- **Small scale**: single instance, no Redis or external state
