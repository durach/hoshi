import asyncio
from unittest.mock import AsyncMock

import pytest

from checkers import CheckerConfig, Checkers
from main import app
from providers import GrammarResult
from store import CheckResult


async def seed_result(store, checker="default"):
    r = CheckResult(username="u", prompt="lets go", has_issues=True,
                    explanation="", checker=checker)
    store.add(r)
    return r


@pytest.mark.asyncio
async def test_checkers_endpoint_lists_names(client, auth, provider):
    auth._tokens = {"tok": "user"}
    resp = await client.get("/api/checkers", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    assert resp.json() == {"checkers": [{"name": "default", "default": True}]}

    resp = await client.get("/api/checkers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_result_is_404(client, auth):
    auth._tokens = {"tok": "user"}
    resp = await client.post(
        "/api/results/999/checks",
        json={"checker": "default"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_checker_is_422(client, store, auth):
    auth._tokens = {"tok": "user"}
    await seed_result(store)
    resp = await client.post(
        f"/api/results/{store.results[-1].id}/checks",
        json={"checker": "nope"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_own_checker_counts_as_attached(client, store, auth):
    auth._tokens = {"tok": "user"}
    await seed_result(store, checker="default")
    resp = await client.post(
        f"/api/results/{store.results[-1].id}/checks",
        json={"checker": "default"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_opinion_lands_and_rebroadcasts(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    second_provider = AsyncMock()
    second_provider.check_grammar = AsyncMock(
        return_value=GrammarResult(has_issues=False, explanation="")
    )
    app.state.checkers = Checkers(
        providers={"default": provider, "second": second_provider},
        configs={
            "default": CheckerConfig(
                name="default", provider="test", model="test-model", default=True
            ),
            "second": CheckerConfig(
                name="second", provider="test", model="test-model-2", default=False
            ),
        },
        default="default",
    )
    await seed_result(store, checker="default")
    resp = await client.post(
        f"/api/results/{store.results[-1].id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 202
    await asyncio.gather(*app.state.background_tasks)

    result = store.results[-1]
    assert result.opinions[0]["checker"] == "second"
    assert result.opinions[0]["status"] == "clean"
    assert "raw" not in result.opinions[0]
    assert result.debug["opinions"]["second"]["request"]["checker"] == "second"

    resp = await client.post(
        f"/api/results/{result.id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_failed_opinion_is_an_error_opinion(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    second_provider = AsyncMock()
    second_provider.check_grammar = AsyncMock(side_effect=TimeoutError("boom"))
    app.state.checkers = Checkers(
        providers={"default": provider, "second": second_provider},
        configs={
            "default": CheckerConfig(
                name="default", provider="test", model="test-model", default=True
            ),
            "second": CheckerConfig(
                name="second", provider="test", model="test-model-2", default=False
            ),
        },
        default="default",
    )
    await seed_result(store, checker="default")
    resp = await client.post(
        f"/api/results/{store.results[-1].id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 202
    await asyncio.gather(*app.state.background_tasks)

    result = store.results[-1]
    assert result.opinions[0]["checker"] == "second"
    assert result.opinions[0]["status"] == "error"
