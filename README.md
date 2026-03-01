# Hoshi

A grammar teaching tool for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Hooks into your prompts, checks grammar via configurable LLM providers (Anthropic, OpenAI, Gemini), and displays explanations on a real-time web dashboard.

The goal is to help you learn better writing habits — Hoshi explains what's wrong and why, it doesn't rewrite your text.

## How it works

```
Claude Code prompt → async hook (curl) → FastAPI backend → LLM grammar check → WebSocket → Dashboard
```

1. You type a prompt in Claude Code
2. A `UserPromptSubmit` hook fires asynchronously (never blocks your workflow)
3. The server checks grammar via your configured LLM provider
4. Results appear in real-time on a web dashboard

## Quick start

### 1. Configure the server

```bash
cp .env.example .env
cp tokens.json.example tokens.json
```

Edit `.env` with your LLM provider and API key:

```
PROVIDER=openai          # or: anthropic, gemini
MODEL=gpt-4o             # any model from your provider
OPENAI_API_KEY=sk-...    # key for your chosen provider
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=changeme
```

Edit `tokens.json` — map tokens to usernames:

```json
{
  "your-secret-token-here": "yourname"
}
```

### 2. Start the server

```bash
docker compose up -d
```

Dashboard is at `http://localhost:8080` (login with your dashboard credentials).

### 3. Install the hook

```bash
mkdir -p ~/.hoshi
cp hook/hook.sh ~/.hoshi/hook.sh
```

Add to your `~/.zshrc` (or `~/.bashrc`):

```bash
export HOSHI_SERVER_URL="http://your-server:8080"
export HOSHI_TOKEN="your-secret-token-here"
```

Add the hook to `~/.claude/settings.json`:

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

Reload your shell and start using Claude Code — grammar check results will appear on the dashboard.

## Supported providers

| Provider | `PROVIDER` | `MODEL` example | API key env var |
|----------|-----------|-----------------|-----------------|
| Anthropic | `anthropic` | `claude-sonnet-4-5-20250929` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| Google Gemini | `gemini` | `gemini-2.0-flash` | `GEMINI_API_KEY` |

Only set the API key for the provider you're using.

## Development

```bash
uv venv .venv
source .venv/bin/activate
cd backend && uv pip install -r requirements.txt
python -m pytest -v
```

## Project structure

```
hoshi/
├── backend/
│   ├── main.py              # FastAPI app (/api/check, /api/health, /ws)
│   ├── auth.py              # Bearer token validation
│   ├── config.py            # Settings from env vars
│   ├── store.py             # In-memory store + WebSocket broadcast
│   ├── providers/
│   │   ├── __init__.py      # GrammarProvider protocol + factory
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── gemini.py
│   └── tests/
├── frontend/
│   ├── nginx.conf           # Reverse proxy + basic auth
│   └── static/              # Dashboard (HTML/JS/CSS)
├── hook/
│   └── hook.sh              # Claude Code hook script
├── docker-compose.yml
├── .env.example
└── tokens.json.example
```

## License

MIT
