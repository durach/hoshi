from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from auth import TokenAuth
from main import app
from store import ResultStore


@pytest.fixture
def ws_app():
    """Set up app state for WebSocket tests."""
    app.state.background_tasks = set()
    app.state.store = ResultStore()
    a = TokenAuth.__new__(TokenAuth)
    a._tokens = {"valid_token": "alice"}
    app.state.auth = a
    app.state.provider = MagicMock()
    return app


def test_ws_rejects_without_token(ws_app):
    client = TestClient(ws_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_ws_rejects_invalid_token(ws_app):
    client = TestClient(ws_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=bad_token"):
            pass


def test_ws_accepts_valid_token(ws_app):
    client = TestClient(ws_app)
    with client.websocket_connect("/ws?token=valid_token") as ws:
        assert ws is not None
