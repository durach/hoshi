from unittest.mock import patch

import pytest

from main import _run_check
from providers import GrammarResult


class _RaisingProvider:
    """A provider that fails the way a timeout or a schema rejection does."""

    async def check_grammar(self, _prompt):
        raise TimeoutError("provider timed out")


class _StubProvider:
    def __init__(self, result):
        self._result = result

    async def check_grammar(self, _prompt):
        return self._result


@pytest.mark.asyncio
async def test_check_returns_202(client, auth):
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.post(
            "/api/check",
            json={"prompt": "He go to store"},
            headers={"Authorization": "Bearer tok_test"},
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_check_invalid_token(client, auth):
    with patch.object(auth, "validate", return_value=None):
        resp = await client.post(
            "/api/check",
            json={"prompt": "Hello"},
            headers={"Authorization": "Bearer invalid"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_missing_auth(client):
    resp = await client.post("/api/check", json={"prompt": "Hello"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_rejects_non_slug_agent(client, auth):
    """The agent name becomes a CSS class on the dashboard, so it stays a slug."""
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.post(
            "/api/check",
            json={"prompt": "Hello", "agent": "codex\"><script>"},
            headers={"Authorization": "Bearer tok_test"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_a_failing_provider_still_yields_a_result(store):
    await _run_check(store, _RaisingProvider(), "alice", "He go to store")

    stored = store.results[-1]
    assert stored.status == "error"
    # The formatted message says what went wrong; the type says what kind of
    # wrong, which is what tells a timeout from a schema rejection.
    assert stored.debug["error"]["type"] == "TimeoutError"
    assert stored.debug["error"]["message"] == "provider timed out"
    assert "provider timed out" in stored.explanation


@pytest.mark.asyncio
async def test_a_successful_check_captures_the_whole_debug_record(store):
    result = GrammarResult(
        has_issues=True,
        explanation="",
        types=["grammar"],
        issues=[{"type": "grammar", "note": "subject-verb agreement"}],
        correction='He <mark data-type="grammar">goes</mark> to the store',
        raw={"issues": [{"type": "grammar", "note": "subject-verb agreement"}]},
        usage={"input_tokens": 12, "output_tokens": 8},
    )

    await _run_check(
        store,
        _StubProvider(result),
        "alice",
        "He go to store",
        provider_name="openai",
        model="gpt-5.6-terra",
    )

    stored = store.results[-1]
    assert stored.status == "issues"
    assert {"request", "raw", "timing", "analysis"} <= set(stored.debug)
    assert stored.debug["request"]["model"] == "gpt-5.6-terra"
    assert stored.debug["raw"] == result.raw
    assert stored.debug["timing"]["usage"] == {"input_tokens": 12, "output_tokens": 8}
    assert stored.debug["analysis"]["no_op"] is False
