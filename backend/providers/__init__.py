from dataclasses import dataclass
from typing import Protocol


@dataclass
class GrammarResult:
    has_issues: bool
    explanation: str

SYSTEM_PROMPT = (
    "Check the grammar of the following text. Explain issues if you find. "
    'Respond with JSON: {"has_issues": true/false, "explanation": "markdown text"}'
)


class GrammarProvider(Protocol):
    async def check_grammar(self, text: str) -> GrammarResult: ...


def create_provider(
    provider: str,
    model: str,
    *,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    gemini_api_key: str = "",
) -> GrammarProvider:
    match provider:
        case "anthropic":
            from providers.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=anthropic_api_key, model=model)
        case "openai":
            from providers.openai import OpenAIProvider
            return OpenAIProvider(api_key=openai_api_key, model=model)
        case "gemini":
            from providers.gemini import GeminiProvider
            return GeminiProvider(api_key=gemini_api_key, model=model)
        case _:
            raise ValueError(f"Unknown provider: {provider}")
