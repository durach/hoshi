#!/bin/bash
# Tests for .githooks/pre-push.
#
# Every case asserts the EXIT CODE, not the message. Two bugs during
# development printed "BLOCKED" and then exited 0 — a guard that refuses in
# words and consents in its exit code is worse than no guard, and only an
# exit-code assertion catches it.
#
# Runs entirely inside a throwaway repository: a test that commits into the
# real one is a test nobody dares run.

set -uo pipefail

HOOK="$(cd "$(dirname "$0")/.." && pwd)/.githooks/pre-push"
WORK="${TMPDIR:-/tmp}/hoshi-pre-push-test.$$"
ZERO='0000000000000000000000000000000000000000'
passed=0
failed=0

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

setup() {
    rm -rf "$WORK"
    mkdir -p "$WORK" || exit 1
    cd "$WORK" || exit 1
    git init -q .
    git config user.email test@example.com
    git config user.name Test
    git config commit.gpgsign false
    printf 'hello world\n' >README.md
    git add README.md
    git commit -q -m "initial"
    BASE="$(git rev-parse HEAD)"
    printf '# terms\nzarquon\nbetelgeuse\n' >"$WORK/denylist.txt"
    export HOSHI_DENYLIST="$WORK/denylist.txt"
}

# check <description> <expected-exit> <ref-name> [remote-sha]
check() {
    local desc="$1" want="$2" ref="$3" remote="${4:-$BASE}" got line
    line="$(printf 'refs/heads/%s %s refs/heads/%s %s' \
        "$ref" "$(git rev-parse HEAD)" "$ref" "$remote")"
    # A here-string, not a pipe: under `set -o pipefail` a hook that exits
    # without draining stdin gives its writer SIGPIPE, and the pipeline reports
    # 141 instead of the hook's own status.
    "$HOOK" origin git@example.com:test/test.git <<<"$line" >/dev/null 2>&1
    got=$?
    if [ "$got" -eq "$want" ]; then
        printf '  ok    %s (exit %s)\n' "$desc" "$got"
        passed=$((passed + 1))
    else
        printf '  FAIL  %s — wanted exit %s, got %s\n' "$desc" "$want" "$got"
        failed=$((failed + 1))
    fi
}

setup
check "clean push is allowed" 0 main

setup
printf 'KEY=sk-TESTONLYnotarealkey000000\n' >leak.txt  # privacy-guard-allow
git add leak.txt && git commit -q -m "credential"
check "credential in a pushed file is blocked" 1 main

setup
printf 'notes on the Betelgeuse integration\n' >scratch.txt  # privacy-guard-allow
git add scratch.txt && git commit -q -m "add"
git rm -q scratch.txt && git commit -q -m "remove"
check "denylist term added then deleted is still blocked" 1 main

setup
printf 'see /Users/someone/Projects/thing\n' >path.txt  # privacy-guard-allow
git add path.txt && git commit -q -m "path"
check "real home-directory path is blocked" 1 main

setup
printf 'the docs example /Users/me/notes.md is fine\n' >ok.txt
git add ok.txt && git commit -q -m "example path"
check "the invented /Users/me path is allowed" 0 main

setup
check "pushing a backup ref is blocked" 1 pre-sanitize-backup "$ZERO"

setup
mkdir -p .proto && printf 'x = 1\n' >.proto/check.py
git add .proto/check.py && git commit -q -m "prototype"
check "scratch directory in the tree is blocked" 1 main

setup
printf 'KEY=sk-TESTONLYnotarealkey000000\n' >leak.txt  # privacy-guard-allow
git add leak.txt && git commit -q -m "credential"
HOSHI_DENYLIST=/nonexistent check "credentials are caught without a denylist" 1 main

setup
printf 'KEY=sk-TESTONLYnotarealkey000000\n' >leak.txt  # privacy-guard-allow
git add leak.txt && git commit -q -m "credential"
PRIVACY_GUARD=off check "the documented override lets a push through" 0 main

setup
printf 'KEY=sk-TESTONLYnotarealkey000000 # privacy-guard-allow\n' >marked.txt # privacy-guard-allow
git add marked.txt && git commit -q -m "marked fixture"
check "a line carrying the allow marker is skipped" 0 main

setup
{
    printf 'KEY=sk-TESTONLYnotarealkey000000 # privacy-guard-allow\n' # privacy-guard-allow
    printf 'KEY=sk-TESTONLYnotarealkey111111\n'                       # privacy-guard-allow
} >mixed.txt
git add mixed.txt && git commit -q -m "one marked, one not"
check "the marker exempts only its own line" 1 main

printf '\n%s passed, %s failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
