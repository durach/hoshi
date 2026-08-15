from unittest.mock import patch

import pytest

from store import CheckResult


@pytest.mark.asyncio
async def test_debug_requires_auth(client, store):
    store.add(CheckResult(username="a", prompt="p", has_issues=False, explanation=""))
    resp = await client.get("/api/results/1/debug")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_debug_returns_the_captured_record(client, auth, store):
    store.add(
        CheckResult(
            username="a",
            prompt="p",
            has_issues=False,
            explanation="",
            debug={"request": {"model": "gpt-5.6-terra"}},
        )
    )
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results/1/debug", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json()["request"]["model"] == "gpt-5.6-terra"


@pytest.mark.asyncio
async def test_debug_404_for_unknown_id(client, auth, store):
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results/999/debug", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_debug_empty_object_when_nothing_was_captured(client, auth, store):
    store.add(CheckResult(username="a", prompt="p", has_issues=False, explanation=""))
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results/1/debug", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_system_prompt_is_served_whole(client, auth):
    from providers import SYSTEM_PROMPT, SYSTEM_PROMPT_HASH

    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/debug/system-prompt", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"hash": SYSTEM_PROMPT_HASH, "text": SYSTEM_PROMPT}


@pytest.mark.asyncio
async def test_system_prompt_requires_auth(client):
    resp = await client.get("/api/debug/system-prompt")
    assert resp.status_code == 401
