from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CheckResult:
    username: str
    prompt: str
    has_issues: bool
    explanation: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "prompt": self.prompt,
            "has_issues": self.has_issues,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }


class ResultStore:
    def __init__(self):
        self.results: list[CheckResult] = []
        self._connections: list = []

    def add(self, result: CheckResult):
        self.results.append(result)

    def connect(self, websocket):
        self._connections.append(websocket)

    def disconnect(self, websocket):
        self._connections.remove(websocket)

    async def add_and_broadcast(self, result: CheckResult):
        self.add(result)
        data = result.to_dict()
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)
