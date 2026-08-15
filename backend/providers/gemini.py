from google import genai

from providers import (
    GRAMMAR_SCHEMA,
    SYSTEM_PROMPT,
    GrammarResult,
    build_result,
    parse_provider_json,
)


def _strip_additional_properties(node: object) -> object:
    """Gemini's response_schema rejects additionalProperties, at any depth.

    The key appears on both the root object and the nested issue object, so a
    shallow copy is not enough. Everything else, the enum included, carries over.
    """
    if isinstance(node, dict):
        return {
            k: _strip_additional_properties(v)
            for k, v in node.items()
            if k != "additionalProperties"
        }
    if isinstance(node, list):
        return [_strip_additional_properties(v) for v in node]
    return node


GEMINI_SCHEMA = _strip_additional_properties(GRAMMAR_SCHEMA)


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=text,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=GEMINI_SCHEMA,
            ),
        )
        if response.text is None:
            raise ValueError("Gemini returned empty content")
        return build_result(parse_provider_json(response.text))
