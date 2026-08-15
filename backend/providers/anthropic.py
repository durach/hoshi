from typing import Any, cast

import anthropic
from anthropic.types import ToolUseBlock

from providers import GRAMMAR_SCHEMA, SYSTEM_PROMPT, GrammarResult, build_result


TOOL_NAME = "report_grammar"


class AnthropicProvider:
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def check_grammar(self, text: str) -> GrammarResult:
        # A forced tool call is Anthropic's structured-output mechanism: the
        # model fills the schema instead of writing JSON into prose, so there is
        # no markdown fence to strip and no off-vocabulary type.
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            tools=[
                {
                    "name": TOOL_NAME,
                    "description": "Report the outcome of the grammar check.",
                    "input_schema": GRAMMAR_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )
        block = next((b for b in response.content if isinstance(b, ToolUseBlock)), None)
        if block is None:
            raise TypeError("Expected a tool_use block from Anthropic")
        # block.input is typed `object`; the forced schema guarantees its shape.
        return build_result(cast("dict[str, Any]", block.input))
