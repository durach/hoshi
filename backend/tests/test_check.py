from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client():
    # Patch SDK constructors before importing main (which creates provider at module level)
    with patch("providers.anthropic.anthropic.AsyncAnthropic"), \
         patch("providers.openai.openai.AsyncOpenAI"), \
         patch("providers.gemini.genai.Client"):
        from main import app, store, auth
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, store, auth


@pytest.mark.asyncio
async def test_check_returns_202(client):
    c, store, auth = client
    with patch.object(auth, "validate", return_value="alice"):
        resp = await c.post(
            "/api/check",
            json={"prompt": "He go to store"},
            headers={"Authorization": "Bearer tok_test"},
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_check_invalid_token(client):
    c, store, auth = client
    with patch.object(auth, "validate", return_value=None):
        resp = await c.post(
            "/api/check",
            json={"prompt": "Hello"},
            headers={"Authorization": "Bearer invalid"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_missing_auth(client):
    c, store, auth = client
    resp = await c.post("/api/check", json={"prompt": "Hello"})
    assert resp.status_code == 401
