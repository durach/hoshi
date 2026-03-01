from unittest.mock import patch

import pytest


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
