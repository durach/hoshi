import asyncio
from collections import deque
from unittest.mock import AsyncMock, patch

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
    ws = AsyncMock()
    store.connect(ws)
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
    assert isinstance(result.opinions[0]["elapsed_ms"], int)
    assert "raw" not in result.opinions[0]
    assert result.debug["opinions"]["second"]["request"]["checker"] == "second"
    ws.send_json.assert_awaited_once_with(result.to_dict())

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
    ws = AsyncMock()
    store.connect(ws)
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
    ws.send_json.assert_awaited_once_with(result.to_dict())


def _second_checkers(provider, second_provider):
    return Checkers(
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


@pytest.mark.asyncio
async def test_second_click_while_opinion_in_flight_is_422(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_check(_prompt):
        started.set()
        await release.wait()
        return GrammarResult(has_issues=False, explanation="")

    second_provider = AsyncMock()
    second_provider.check_grammar = slow_check
    app.state.checkers = _second_checkers(provider, second_provider)
    target = await seed_result(store, checker="default")

    resp = await client.post(
        f"/api/results/{target.id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 202
    await started.wait()

    resp = await client.post(
        f"/api/results/{target.id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 422

    release.set()
    await asyncio.gather(*app.state.background_tasks)


@pytest.mark.asyncio
async def test_in_flight_cleared_after_completion(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    second_provider = AsyncMock()
    second_provider.check_grammar = AsyncMock(
        return_value=GrammarResult(has_issues=False, explanation="")
    )
    app.state.checkers = _second_checkers(provider, second_provider)
    target = await seed_result(store, checker="default")

    resp = await client.post(
        f"/api/results/{target.id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 202
    await asyncio.gather(*app.state.background_tasks)
    assert (target.id, "second") not in app.state.in_flight_opinions

    # A stuck entry would only ever block this exact (result, checker) pair —
    # prove the set is actually empty, not just keyed differently.
    other = await seed_result(store, checker="default")
    resp = await client.post(
        f"/api/results/{other.id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 202
    await asyncio.gather(*app.state.background_tasks)


@pytest.mark.asyncio
async def test_in_flight_cleared_after_exception(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    second_provider = AsyncMock()
    app.state.checkers = _second_checkers(provider, second_provider)
    target = await seed_result(store, checker="default")

    with patch("main._perform_check", AsyncMock(side_effect=RuntimeError("boom"))):
        resp = await client.post(
            f"/api/results/{target.id}/checks",
            json={"checker": "second"},
            headers={"Authorization": "Bearer tok"},
        )
        assert resp.status_code == 202
        with pytest.raises(RuntimeError, match="boom"):
            await asyncio.gather(*app.state.background_tasks)

    assert (target.id, "second") not in app.state.in_flight_opinions
    assert target.opinions == []


@pytest.mark.asyncio
async def test_opinion_dropped_if_result_evicted_while_running(client, store, auth, provider):
    auth._tokens = {"tok": "user"}
    store.results = deque(maxlen=2)
    release = asyncio.Event()

    async def slow_check(_prompt):
        await release.wait()
        return GrammarResult(has_issues=False, explanation="")

    second_provider = AsyncMock()
    second_provider.check_grammar = slow_check
    app.state.checkers = _second_checkers(provider, second_provider)
    target = await seed_result(store, checker="default")

    resp = await client.post(
        f"/api/results/{target.id}/checks",
        json={"checker": "second"},
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 202

    # Two more results push target out of the capped deque while its opinion
    # is still in flight.
    await seed_result(store, checker="default")
    await seed_result(store, checker="default")
    assert target not in store.results

    ws = AsyncMock()
    store.connect(ws)
    release.set()
    await asyncio.gather(*app.state.background_tasks)

    assert target.opinions == []
    ws.send_json.assert_not_awaited()
