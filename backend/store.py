import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


MAX_RESULTS = 1000


@dataclass
class CheckResult:
    username: str
    prompt: str
    has_issues: bool
    explanation: str
    status: str = ""
    timestamp: str = ""
    id: int = 0
    project: str = ""
    agent: str = ""
    # Which named checker produced the verdict, and any second opinions
    # attached later — one per checker name, shaped like the fields the
    # dashboard renders for the main verdict.
    checker: str = ""
    opinions: list[dict[str, Any]] = field(default_factory=list)
    # Wall time of the provider call. Also inside debug.timing, but debug never
    # rides the WebSocket, and the dashboard shows a time per verdict.
    elapsed_ms: int = 0
    run_id: str = ""
    types: list[str] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)
    correction: str = ""
    # The correction against the original, segment by segment. This is what the
    # dashboard renders — the marked-up `correction` is kept because the diff is
    # derived from it, not because anything displays it.
    diff: list[dict[str, str]] = field(default_factory=list)
    # Everything captured about how this result was produced. Deliberately kept
    # out of to_dict(): it is fetched per result when a panel is opened.
    debug: dict[str, Any] | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()
        if not self.status:
            self.status = "issues" if self.has_issues else "clean"

    def has_ghost_marks(self) -> bool:
        """Whether analysis found a marked span that changed nothing."""
        if not self.debug:
            return False
        analysis = self.debug.get("analysis") or {}
        return bool(analysis.get("ghost_marks"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "username": self.username,
            "project": self.project,
            "agent": self.agent,
            "checker": self.checker,
            "prompt": self.prompt,
            "has_issues": self.has_issues,
            "explanation": self.explanation,
            "status": self.status,
            "types": list(self.types),
            "issues": [dict(i) for i in self.issues],
            "correction": self.correction,
            "diff": [dict(s) for s in self.diff],
            "has_ghost_marks": self.has_ghost_marks(),
            "opinions": [dict(o) for o in self.opinions],
            "elapsed_ms": self.elapsed_ms,
            "timestamp": self.timestamp,
        }


class ResultStore:
    def __init__(self):
        self.results: deque[CheckResult] = deque(maxlen=MAX_RESULTS)
        self._connections: set = set()
        self._next_id = 0
        # Identifies this process. Results live in memory only, so ids restart
        # at 1 whenever the backend does. A client that dedups on id alone would
        # then silently discard every new result as one it had already seen —
        # it compares run_id to know when to drop its state and start over.
        self.run_id = uuid.uuid4().hex[:12]

    def add(self, result: CheckResult):
        self._next_id += 1
        result.id = self._next_id
        result.run_id = self.run_id
        self.results.append(result)

    def connect(self, websocket):
        self._connections.add(websocket)

    def disconnect(self, websocket):
        self._connections.discard(websocket)

    async def broadcast(self, result: CheckResult):
        data = result.to_dict()
        dead = []
        # Snapshot the set: sending yields to the event loop, which may
        # connect/disconnect clients and mutate _connections mid-iteration.
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    async def add_and_broadcast(self, result: CheckResult):
        self.add(result)
        await self.broadcast(result)
