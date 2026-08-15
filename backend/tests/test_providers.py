import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import ToolUseBlock

from providers import SYSTEM_PROMPT, build_result, create_provider, parse_provider_json


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
        ToolUseBlock(
            type="tool_use",
            id="tu_1",
            name="report_grammar",
            input={
                "issues": [{"type": "grammar", "note": "Use *goes* instead of *go*."}],
                "correction": "he <mark>goes</mark>",
            },
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
    assert result.types == ["grammar"]
    assert "goes" in result.issues[0]["note"]


@pytest.mark.asyncio
async def test_anthropic_provider_no_issues():
    mock_response = MagicMock()
    mock_response.content = [
        ToolUseBlock(
            type="tool_use",
            id="tu_2",
            name="report_grammar",
            input={"issues": [], "correction": ""},
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
    mock_choice.message.content = (
        '{"issues": [{"type": "grammar", "note": "Fix grammar."}], "correction": "x"}'
    )
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
    mock_response.text = '{"issues": [], "correction": ""}'

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


# --- build_result: flags are derived, not taken from the model ---


def test_build_result_derives_flags():
    r = build_result(
        {
            "issues": [
                {"type": "grammar", "note": "a"},
                {"type": "style", "note": "b"},
            ],
            "correction": "fixed",
        }
    )
    assert r.has_issues is True
    assert r.types == ["grammar", "style"]
    assert r.correction == "fixed"


def test_style_alone_is_not_an_issue():
    """A style note is a remark; it must not turn the entry red."""
    r = build_result({"issues": [{"type": "style", "note": "wordy"}], "correction": ""})
    assert r.has_issues is False
    assert r.types == ["style"]


def test_build_result_drops_unknown_types():
    r = build_result(
        {
            "issues": [
                {"type": "grammar", "note": "a"},
                {"type": "vibes", "note": "b"},
            ],
            "correction": "",
        }
    )
    assert [i["type"] for i in r.issues] == ["grammar"]


def test_build_result_handles_empty():
    r = build_result({"issues": [], "correction": ""})
    assert r.has_issues is False
    assert r.types == []


def test_build_result_keeps_the_raw_response():
    data = {"issues": [{"type": "grammar", "note": "n"}], "correction": "c"}
    assert build_result(data).raw == data


def test_build_result_records_what_it_dropped():
    # build_result silently filters types outside ISSUE_TYPES. Silently is the
    # problem: a model emitting a new category vanished without trace.
    data = {
        "issues": [
            {"type": "grammar", "note": "kept"},
            {"type": "clarity", "note": "dropped"},
        ],
        "correction": "",
    }
    result = build_result(data)
    assert [i["note"] for i in result.issues] == ["kept"]
    assert result.dropped_issues == [{"type": "clarity", "note": "dropped"}]


def test_system_prompt_hash_is_stable_and_short():
    from providers import SYSTEM_PROMPT_HASH

    assert len(SYSTEM_PROMPT_HASH) == 8
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8] == SYSTEM_PROMPT_HASH
