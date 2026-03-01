#!/bin/bash
# Hoshi grammar check hook for Claude Code
# Env vars required: HOSHI_SERVER_URL, HOSHI_TOKEN

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt')

# Skip empty prompts
[ -z "$PROMPT" ] && exit 0

curl -s -X POST "$HOSHI_SERVER_URL/api/check" \
  -H "Authorization: Bearer $HOSHI_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": $(echo "$PROMPT" | jq -Rs .)}" \
  >/dev/null 2>&1 &
