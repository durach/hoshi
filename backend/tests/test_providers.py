from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock

from providers import create_provider, parse_provider_json


# --- parse_provider_json tests ---


def test_parse_clean_json():
    raw = '{"has_issues": false, "explanation": ""}'
    assert parse_provider_json(raw) == {"has_issues": False, "explanation": ""}


def test_parse_markdown_fenced_json():
    raw = '```json\n{"has_issues": true, "explanation": "bad grammar"}\n```'
    assert parse_provider_json(raw) == {
        "has_issues": True,
        "explanation": "bad grammar",
    }


def test_parse_invalid_json_raises_valueerror():
    with pytest.raises(ValueError, match="Provider returned invalid JSON"):
        parse_provider_json("Sure! Here is the result...")


@pytest.mark.asyncio
async def test_anthropic_provider_parses_response():
    mock_response = MagicMock()
    mock_response.content = [
        TextBlock(
            type="text",
            text='{"has_issues": true, "explanation": "Use *goes* instead of *go*."}',
        )
    ]

    with patch("providers.anthropic.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        from providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(
            api_key="fake-key", model="claude-sonnet-4-5-20250929"
        )
        result = await provider.check_grammar("He go to the store")

    assert result.has_issues is True
    assert "goes" in result.explanation


@pytest.mark.asyncio
async def test_anthropic_provider_no_issues():
    mock_response = MagicMock()
    mock_response.content = [
        TextBlock(
            type="text",
            text='{"has_issues": false, "explanation": "No issues found."}',
        )
    ]

    with patch("providers.anthropic.anthropic.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        from providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(
            api_key="fake-key", model="claude-sonnet-4-5-20250929"
        )
        result = await provider.check_grammar("The cat sat on the mat.")

    assert result.has_issues is False


@pytest.mark.asyncio
async def test_openai_provider_parses_response():
    mock_choice = MagicMock()
    mock_choice.message.content = '{"has_issues": true, "explanation": "Fix grammar."}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch("providers.openai.openai.AsyncOpenAI") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        from providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="fake-key", model="gpt-4o")
        result = await provider.check_grammar("He go to store")

    assert result.has_issues is True


@pytest.mark.asyncio
async def test_gemini_provider_parses_response():
    mock_response = MagicMock()
    mock_response.text = '{"has_issues": false, "explanation": "All good."}'

    with patch("providers.gemini.genai.Client") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        from providers.gemini import GeminiProvider

        provider = GeminiProvider(api_key="fake-key", model="gemini-2.0-flash")
        result = await provider.check_grammar("The cat sat on the mat.")

    assert result.has_issues is False


# --- Factory tests ---


def test_create_anthropic_provider():
    with patch("providers.anthropic.anthropic.AsyncAnthropic"):
        from providers.anthropic import AnthropicProvider

        p = create_provider(
            "anthropic", "claude-sonnet-4-5-20250929", anthropic_api_key="key"
        )
        assert isinstance(p, AnthropicProvider)


def test_create_openai_provider():
    with patch("providers.openai.openai.AsyncOpenAI"):
        from providers.openai import OpenAIProvider

        p = create_provider("openai", "gpt-4o", openai_api_key="key")
        assert isinstance(p, OpenAIProvider)


def test_create_gemini_provider():
    with patch("providers.gemini.genai.Client"):
        from providers.gemini import GeminiProvider

        p = create_provider("gemini", "gemini-2.0-flash", gemini_api_key="key")
        assert isinstance(p, GeminiProvider)


def test_create_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("unknown", "model")
