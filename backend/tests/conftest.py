from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from auth import TokenAuth
from main import app
from store import ResultStore


@pytest_asyncio.fixture
async def store():
    s = ResultStore()
    app.state.store = s
    yield s


@pytest_asyncio.fixture
async def auth():
    a = TokenAuth.__new__(TokenAuth)
    a._tokens = {}
    app.state.auth = a
    yield a


@pytest_asyncio.fixture
async def provider():
    p = MagicMock()
    app.state.provider = p
    yield p


@pytest_asyncio.fixture
async def client(store, auth, provider):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
