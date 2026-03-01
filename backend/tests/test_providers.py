from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from providers import GrammarResult


@pytest.mark.asyncio
async def test_anthropic_provider_parses_response():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text='{"has_issues": true, "explanation": "Use *goes* instead of *go*."}')
    ]

    with patch("providers.anthropic.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        from providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-4-5-20250929")
        result = await provider.check_grammar("He go to the store")

    assert result.has_issues is True
    assert "goes" in result.explanation


@pytest.mark.asyncio
async def test_anthropic_provider_no_issues():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text='{"has_issues": false, "explanation": "No issues found."}')
    ]

    with patch("providers.anthropic.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        from providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key="fake-key", model="claude-sonnet-4-5-20250929")
        result = await provider.check_grammar("The cat sat on the mat.")

    assert result.has_issues is False
