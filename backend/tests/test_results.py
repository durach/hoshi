from unittest.mock import patch

import pytest

from store import CheckResult


@pytest.mark.asyncio
async def test_results_requires_auth(client):
    resp = await client.get("/api/results")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_results_rejects_invalid_token(client, auth):
    with patch.object(auth, "validate", return_value=None):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer invalid"}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_results_empty_when_nothing_stored(client, auth):
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_results_returns_stored_oldest_first(client, auth, store):
    for i in range(3):
        store.add(
            CheckResult(
                username="alice",
                prompt=f"prompt {i}",
                has_issues=False,
                explanation="",
            )
        )

    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer tok_test"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert [r["prompt"] for r in body] == ["prompt 0", "prompt 1", "prompt 2"]
    assert [r["id"] for r in body] == [1, 2, 3]
    assert body[0]["status"] == "clean"


@pytest.mark.asyncio
async def test_project_is_stored_and_served(client, auth, store):
    store.add(
        CheckResult(
            username="alice",
            prompt="he go there",
            has_issues=True,
            explanation="",
            project="hoshi",
        )
    )
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.json()[0]["project"] == "hoshi"


@pytest.mark.asyncio
async def test_project_defaults_to_empty(client, auth, store):
    store.add(CheckResult(username="a", prompt="p", has_issues=False, explanation=""))
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.json()[0]["project"] == ""


@pytest.mark.asyncio
async def test_agent_is_stored_and_served(client, auth, store):
    store.add(
        CheckResult(
            username="alice",
            prompt="he go there",
            has_issues=True,
            explanation="",
            agent="codex",
        )
    )
    with patch.object(auth, "validate", return_value="alice"):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.json()[0]["agent"] == "codex"


@pytest.mark.asyncio
async def test_agent_defaults_to_empty(client, auth, store):
    store.add(CheckResult(username="a", prompt="p", has_issues=False, explanation=""))
    with patch.object(auth, "validate", return_value="a"):
        resp = await client.get(
            "/api/results", headers={"Authorization": "Bearer tok_test"}
        )
    assert resp.json()[0]["agent"] == ""
