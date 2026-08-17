from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from auth import TokenAuth
from config import Settings
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
    from checkers import CheckerConfig, Checkers

    p = MagicMock()
    app.state.checkers = Checkers(
        providers={"default": p},
        configs={
            "default": CheckerConfig(
                name="default", provider="test", model="test-model", default=True
            )
        },
        default="default",
    )
    yield p


@pytest_asyncio.fixture
async def settings():
    s = Settings()
    app.state.settings = s
    yield s


@pytest_asyncio.fixture
async def client(store, auth, provider, settings):
    app.state.background_tasks = set()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
