from unittest.mock import patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Patch SDK constructors before main.py module-level code runs
with patch("providers.anthropic.anthropic.AsyncAnthropic"), \
     patch("providers.openai.openai.AsyncOpenAI"), \
     patch("providers.gemini.genai.Client"):
    from main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
