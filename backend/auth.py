import json
from pathlib import Path


class TokenAuth:
    def __init__(self, tokens_file: str):
        path = Path(tokens_file)
        if path.exists():
            self._tokens: dict[str, str] = json.loads(path.read_text())
        else:
            self._tokens = {}

    def validate(self, token: str) -> str | None:
        if not token:
            return None
        return self._tokens.get(token)
