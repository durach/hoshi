import json

from google import genai

from providers import GrammarResult, SYSTEM_PROMPT


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.models.generate_content_async(
            model=self._model,
            contents=text,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        data = json.loads(response.text)
        return GrammarResult(
            has_issues=data["has_issues"],
            explanation=data.get("explanation", ""),
        )
