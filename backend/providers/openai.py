import openai

from providers import SYSTEM_PROMPT, GrammarResult, parse_provider_json


class OpenAIProvider:
    def __init__(self, api_key: str, model: str):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        data = parse_provider_json(response.choices[0].message.content)
        return GrammarResult(
            has_issues=data["has_issues"],
            explanation=data.get("explanation", ""),
        )
