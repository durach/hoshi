import openai

from providers import (
    GRAMMAR_SCHEMA,
    SYSTEM_PROMPT,
    GrammarResult,
    build_result,
    parse_provider_json,
)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        # A local endpoint (Ollama) ignores the key, but the SDK refuses an
        # empty one; "ollama" is the conventional placeholder.
        if base_url and not api_key:
            api_key = "ollama"
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        # strict json_schema: the API rejects output that misses a field or uses
        # a type outside the enum, so the categories cannot drift.
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "grammar_check",
                    "strict": True,
                    "schema": GRAMMAR_SCHEMA,
                },
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI returned empty content")
        result = build_result(parse_provider_json(content))
        # Only OpenAI reports usage in this shape; the other two SDKs differ, so
        # the field stays optional rather than complicating all three.
        if response.usage is not None:
            result.usage = {
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
            }
        return result
