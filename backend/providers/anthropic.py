import json

import anthropic

from providers import GrammarResult, SYSTEM_PROMPT


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        data = json.loads(response.content[0].text)
        return GrammarResult(
            has_issues=data["has_issues"],
            explanation=data.get("explanation", ""),
        )
