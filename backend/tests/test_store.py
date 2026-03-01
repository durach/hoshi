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
        store.add(CheckResult(
            username="u", prompt=f"p{i}", has_issues=False, explanation="",
        ))
    assert len(store.results) == 1000
    assert store.results[0].prompt == "p5"  # oldest 5 evicted


def test_check_result_status_derived_from_has_issues():
    clean = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    assert clean.status == "clean"

    issues = CheckResult(username="u", prompt="p", has_issues=True, explanation="bad")
    assert issues.status == "issues"


def test_check_result_explicit_error_status():
    error = CheckResult(
        username="u", prompt="p", has_issues=False, explanation="fail", status="error",
    )
    assert error.status == "error"


def test_check_result_status_in_dict():
    r = CheckResult(username="u", prompt="p", has_issues=False, explanation="")
    d = r.to_dict()
    assert d["status"] == "clean"
