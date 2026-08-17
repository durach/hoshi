from unittest.mock import AsyncMock

import pytest

from store import CheckResult, ResultStore


@pytest.fixture
def store():
    return ResultStore()


def test_add_result(store):
    result = CheckResult(
        username="alice",
        prompt="He go to store",
        has_issues=True,
        explanation="Grammar issue.",
    )
    store.add(result)
    assert len(store.results) == 1
    assert store.results[0].username == "alice"
    assert store.results[0].timestamp is not None


@pytest.mark.asyncio
async def test_websocket_broadcast(store):
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    store.connect(ws1)
    store.connect(ws2)

    result = CheckResult(
        username="bob",
        prompt="Test",
        has_issues=False,
        explanation="No issues.",
    )
    await store.add_and_broadcast(result)

    assert ws1.send_json.call_count == 1
    assert ws2.send_json.call_count == 1
    sent = ws1.send_json.call_args[0][0]
    assert sent["username"] == "bob"


@pytest.mark.asyncio
async def test_disconnect_removes_ws(store):
    ws = AsyncMock()
    store.connect(ws)
    store.disconnect(ws)

    result = CheckResult(username="x", prompt="y", has_issues=False, explanation="")
    await store.add_and_broadcast(result)

    ws.send_json.assert_not_called()


def test_disconnect_idempotent():
    """Disconnecting a websocket twice should not raise."""
    store = ResultStore()
    sentinel = object()
    store.connect(sentinel)
    store.disconnect(sentinel)
    store.disconnect(sentinel)  # should not raise


def test_results_capped_at_max():
    store = ResultStore()
    for i in range(1005):
        store.add(
            CheckResult(
                username="u",
                prompt=f"p{i}",
                has_issues=False,
                explanation="",
            )
        )
    assert len(store.results) == 1000
    assert store.results[0].prompt == "p5"  # oldest 5 evicted


def test_check_result_status_derived_from_has_issues():
    clean = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    assert clean.status == "clean"

    issues = CheckResult(username="u", prompt="p", has_issues=True, explanation="bad")
    assert issues.status == "issues"


def test_check_result_explicit_error_status():
    error = CheckResult(
        username="u",
        prompt="p",
        has_issues=False,
        explanation="fail",
        status="error",
    )
    assert error.status == "error"


def test_check_result_status_in_dict():
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    d = r.to_dict()
    assert d["status"] == "clean"


def test_add_assigns_monotonic_ids(store):
    for i in range(3):
        store.add(
            CheckResult(username="u", prompt=f"p{i}", has_issues=False, explanation="")
        )
    assert [r.id for r in store.results] == [1, 2, 3]


def test_ids_keep_increasing_past_cap():
    """Ids must not be reused after eviction, or the dashboard would dedup them away."""
    store = ResultStore()
    for i in range(1005):
        store.add(
            CheckResult(username="u", prompt=f"p{i}", has_issues=False, explanation="")
        )
    assert store.results[0].id == 6
    assert store.results[-1].id == 1005


def test_run_id_is_stamped_on_every_result(store):
    for _ in range(3):
        store.add(
            CheckResult(username="u", prompt="p", has_issues=False, explanation="")
        )
    run_ids = {r.run_id for r in store.results}
    assert run_ids == {store.run_id}
    assert store.results[0].to_dict()["run_id"] == store.run_id


def test_restarted_store_reuses_ids_but_not_run_id():
    """Ids collide across restarts, so run_id is what tells a client to reset.

    Without this the dashboard silently drops every result after a backend
    restart: the ids look like ones it has already rendered.
    """
    first = ResultStore()
    first.add(
        CheckResult(username="u", prompt="before", has_issues=False, explanation="")
    )

    second = ResultStore()  # stands in for a restarted backend
    second.add(
        CheckResult(username="u", prompt="after", has_issues=False, explanation="")
    )

    assert first.results[0].id == second.results[0].id == 1
    assert first.run_id != second.run_id


@pytest.mark.asyncio
async def test_broadcast_survives_disconnect_mid_iteration(store):
    """A client disconnecting while a broadcast is in flight must not abort it.

    Each client drops the other, so whichever the set yields first mutates
    _connections before the loop advances — the exact race a live disconnect
    during `await send_json` produces.
    """
    ws_a = AsyncMock()
    ws_b = AsyncMock()

    async def drop_b(_data):
        store.disconnect(ws_b)

    async def drop_a(_data):
        store.disconnect(ws_a)

    ws_a.send_json.side_effect = drop_b
    ws_b.send_json.side_effect = drop_a
    store.connect(ws_a)
    store.connect(ws_b)

    result = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    await store.add_and_broadcast(result)

    assert ws_a.send_json.call_count == 1
    assert ws_b.send_json.call_count == 1


def test_debug_is_not_broadcast():
    # The panel is fetched on demand; shipping it to every client on every
    # check would multiply the payload for something read twice a day.
    result = CheckResult(
        username="a",
        prompt="p",
        has_issues=False,
        explanation="",
        debug={"raw": {"issues": []}},
    )
    assert "debug" not in result.to_dict()
    assert result.debug == {"raw": {"issues": []}}


def test_has_ghost_marks_is_broadcast():
    # The entry marker must be decidable from the broadcast payload, or
    # enabling debug would fire one request per visible entry.
    flagged = CheckResult(
        username="a",
        prompt="p",
        has_issues=True,
        explanation="",
        debug={"analysis": {"ghost_marks": [{"text": "the"}]}},
    )
    assert flagged.to_dict()["has_ghost_marks"] is True


def test_has_ghost_marks_defaults_false_without_debug():
    plain = CheckResult(username="a", prompt="p", has_issues=False, explanation="")
    assert plain.to_dict()["has_ghost_marks"] is False


def test_diff_is_broadcast():
    # Unlike the debug record, the diff is what the dashboard displays, so it
    # rides the normal payload.
    segment = {"op": "replace", "before": "cant", "after": "can't", "type": "grammar"}
    result = CheckResult(
        username="a",
        prompt="p",
        has_issues=True,
        explanation="",
        diff=[segment],
    )
    assert result.to_dict()["diff"] == [segment]


def test_diff_defaults_to_empty():
    plain = CheckResult(username="a", prompt="p", has_issues=False, explanation="")
    assert plain.to_dict()["diff"] == []


def test_to_dict_carries_checker_and_opinions():
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="",
                    checker="terra")
    r.opinions.append({"checker": "qwen8", "has_issues": True, "status": "issues",
                       "types": ["grammar"], "issues": [], "correction": "", "diff": [],
                       "explanation": "", "has_ghost_marks": False, "timestamp": "t"})
    d = r.to_dict()
    assert d["checker"] == "terra"
    assert d["opinions"][0]["checker"] == "qwen8"
    assert "debug" not in d


def test_to_dict_carries_elapsed_ms():
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="",
                    elapsed_ms=2471)
    assert r.to_dict()["elapsed_ms"] == 2471


@pytest.mark.asyncio
async def test_broadcast_resends_without_adding():
    store = ResultStore()
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    store.add(r)
    ws = AsyncMock()
    store.connect(ws)
    await store.broadcast(r)
    assert len(store.results) == 1
    ws.send_json.assert_awaited_once_with(r.to_dict())
