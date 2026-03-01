from dataclasses import dataclass
from typing import Protocol


@dataclass
class GrammarResult:
    has_issues: bool
    explanation: str


class GrammarProvider(Protocol):
    async def check_grammar(self, text: str) -> GrammarResult: ...
