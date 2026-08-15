#!/bin/bash
# Hoshi grammar check hook for Claude Code and Codex CLI (UserPromptSubmit).
#
# Both agents send the same payload fields on stdin — prompt, cwd, session_id,
# transcript_path, hook_event_name — so one script serves both. Codex adds
# turn_id/model/permission_mode, which this hook ignores.
#
# Config: HOSHI_SERVER_URL and HOSHI_TOKEN, taken from the environment if set,
# otherwise from ~/.hoshi/config. The config file matters because Claude Code
# launched from the desktop app never sources your shell rc, so an env-only
# setup would silently do nothing there. Set HOSHI_LOG to record every run.
[ -f "$HOME/.hoshi/config" ] && . "$HOME/.hoshi/config"

# The hook is otherwise completely silent, which makes "did it even fire?"
# unanswerable — a missing dashboard entry looks the same whether the prompt was
# skipped or the hook was never called.
log() {
    [ -n "$HOSHI_LOG" ] || return 0
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$HOSHI_LOG" 2>/dev/null
}

# Never let a grammar check interfere with the prompt: no output, always exit 0.
[ -n "$HOSHI_SERVER_URL" ] && [ -n "$HOSHI_TOKEN" ] || exit 0

# Which agent invoked us, named by the hook config rather than guessed from the
# payload: the two agents send the same fields, and any field that happens to
# distinguish them today is not a promise. Restricted to a slug so it can safely
# become a CSS class on the dashboard.
AGENT="${1:-claude-code}"
case "$AGENT" in
    *[!a-z0-9-]* | "") AGENT="unknown" ;;
esac

INPUT=$(cat)

post() {
    # Fire and forget: detached so it outlives this script, capped so a wedged
    # server cannot leave curl processes accumulating.
    nohup curl -s -m 10 -X POST "$HOSHI_SERVER_URL/api/check" \
        -H "Authorization: Bearer $HOSHI_TOKEN" \
        -H "Content-Type: application/json" \
        --data-binary "$1" \
        >/dev/null 2>&1 &
}

# What is not English the user wrote, and so is never checked:
#   - empty prompts
#   - slash commands: "/daily", "/loop 5m /foo". The first token must hold no
#     further slash, so a prompt opening with an absolute path
#     ("/Users/me/notes.md is wrong") is still checked.
#   - harness injections: "<task-notification>", "<system-reminder>" and the
#     like. The tag must be followed by whitespace, end-of-string or another
#     tag, since these never open a sentence — so asking about
#     "<div>hello</div> why doesnt this render" is still checked.
# Anchored with \A and \z rather than ^ and $, because Oniguruma matches those
# at line breaks and would drop any long prompt containing a line that merely
# starts with a slash or a tag. Defined once; both paths below use it.
JQ_SKIP='def hoshi_skip:
  (. == "")
  or test("\\A/[A-Za-z][A-Za-z0-9_-]*(\\s|\\z)")
  or test("\\A\\s*<[a-zA-Z][a-zA-Z0-9_-]*>(\\s|\\z|<)");'

# The result is labelled with the project it came from: the hook is registered
# globally, so one dashboard shows every session on the machine. Prefer the
# payload's cwd; fall back to the hook's own working directory.
PROJECT=$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
[ -z "$PROJECT" ] && PROJECT="$PWD"
PROJECT=$(basename "$PROJECT")

# --- Catch up on queued messages -------------------------------------------
# Typing while Claude is working enqueues the text instead of submitting it, so
# no UserPromptSubmit fires and those messages would never be checked. Claude
# Code records them in the transcript as queue-operation/enqueue, so replay any
# that appeared since the last run. They arrive one prompt late, which is the
# price of there being no event to hang them on.
#
# Claude Code only: Codex rollout transcripts hold no queue-operation entries,
# so the grep below finds nothing and this whole block quietly does nothing.
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null)
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
NOW=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)

if [ -n "$SESSION" ] && [ -r "$TRANSCRIPT" ]; then
    STATE_DIR="$HOME/.hoshi/state"
    mkdir -p "$STATE_DIR" 2>/dev/null
    STATE="$STATE_DIR/$SESSION"
    # First sight of a session starts the watermark at now: replaying its whole
    # history would flood the dashboard with prompts already long past.
    SINCE=$(cat "$STATE" 2>/dev/null) || SINCE=""
    [ -z "$SINCE" ] && SINCE="$NOW"

    QUEUED=$(grep -F '"queue-operation"' "$TRANSCRIPT" 2>/dev/null | jq -c \
        --arg since "$SINCE" --arg project "$PROJECT" --arg agent "$AGENT" "$JQ_SKIP"'
        select(.type == "queue-operation" and .operation == "enqueue")
        | select(.timestamp > $since)
        | select(((.content // "") | hoshi_skip) | not)
        | {prompt: .content, project: $project, agent: $agent}' 2>/dev/null | head -20)

    if [ -n "$QUEUED" ]; then
        while IFS= read -r item; do
            [ -n "$item" ] || continue
            post "$item"
            log "queued  agent=$AGENT project=$PROJECT :: $(printf '%s' "$item" | jq -r '.prompt' | tr '\n' ' ' | cut -c1-70)"
        done <<<"$QUEUED"
    fi
    printf '%s' "$NOW" >"$STATE" 2>/dev/null
fi

# --- The prompt that actually fired this hook -------------------------------
# Built with jq straight from the payload: round-tripping the prompt through a
# shell variable invites `echo` to eat backslash escapes and leading dashes.
BODY=$(printf '%s' "$INPUT" | jq -c --arg project "$PROJECT" --arg agent "$AGENT" "$JQ_SKIP"'
  if (.prompt // "") | hoshi_skip
  then empty
  else {prompt: .prompt, project: $project, agent: $agent}
  end' 2>/dev/null)

# printf, never echo: the prompt may open with a dash or hold backslashes.
PREVIEW=$(printf '%s' "$INPUT" | jq -r '.prompt // ""' 2>/dev/null | tr '\n' ' ' | cut -c1-70)
EVENT=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // "?"' 2>/dev/null)

if [ -z "$BODY" ]; then
    log "skipped event=$EVENT agent=$AGENT project=$PROJECT :: $PREVIEW"
    exit 0
fi

post "$BODY"
log "sent    event=$EVENT agent=$AGENT project=$PROJECT :: $PREVIEW"
exit 0
