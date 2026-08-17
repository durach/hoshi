import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from analysis import analyse
from auth import TokenAuth
from checkers import load_checkers
from config import Settings
from providers import SYSTEM_PROMPT, SYSTEM_PROMPT_HASH
from store import CheckResult, ResultStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.background_tasks = set()
    app.state.store = ResultStore()
    app.state.auth = TokenAuth(settings.tokens_file)
    app.state.checkers = load_checkers(
        settings.checkers_file,
        fallback_provider=settings.provider,
        fallback_model=settings.model,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        gemini_api_key=settings.gemini_api_key,
    )
    app.state.settings = settings
    yield


app = FastAPI(title="Hoshi", lifespan=lifespan)


class CheckRequest(BaseModel):
    prompt: str
    project: str = ""
    # Which agent the prompt was typed into, as named by its hook config. The
    # dashboard turns it into a CSS class, so keep it to a slug.
    agent: str = Field(default="", pattern=r"^[a-z0-9-]*$", max_length=32)


def require_username(request: Request, authorization: str = Header(default="")) -> str:
    """Resolve the bearer token to a username, or reject with 401."""
    token = authorization.removeprefix("Bearer ").strip()
    username = request.app.state.auth.validate(token)
    if not username:
        raise HTTPException(status_code=401, detail="unauthorized")
    return str(username)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/results")
async def results(
    request: Request,
    _username: str = Depends(require_username),
):
    """Oldest-first snapshot of retained results, for dashboard bootstrap."""
    return [r.to_dict() for r in request.app.state.store.results]


@app.get("/api/results/{result_id}/debug")
async def result_debug(
    result_id: int,
    request: Request,
    _username: str = Depends(require_username),
):
    """Everything captured about one check.

    Ids restart with every backend run, so this resolves against the running
    process's store — the only one that exists.
    """
    for result in request.app.state.store.results:
        if result.id == result_id:
            return result.debug or {}
    raise HTTPException(status_code=404, detail="not found")


@app.get("/api/debug/system-prompt")
async def system_prompt(_username: str = Depends(require_username)):
    """The prompt behind every result, stored per result only as a hash."""
    return {"hash": SYSTEM_PROMPT_HASH, "text": SYSTEM_PROMPT}


@app.post("/api/check", status_code=202)
async def check(
    request: Request,
    body: CheckRequest,
    username: str = Depends(require_username),
):
    checkers = request.app.state.checkers
    name = checkers.default
    cfg = checkers.configs[name]
    task = asyncio.create_task(
        _run_check(
            request.app.state.store,
            checkers.providers[name],
            username,
            body.prompt,
            body.project,
            body.agent,
            checker=name,
            provider_name=cfg.provider,
            model=cfg.model,
        )
    )
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return {"status": "accepted"}


async def _perform_check(provider, prompt: str, request_meta: dict) -> tuple[dict, dict]:
    """Run one checker over one prompt.

    Returns (fields, debug): fields is what a verdict looks like wherever it
    lands — a fresh CheckResult or an opinion on an existing one — and debug is
    the record that never rides the WebSocket.
    """
    started = time.perf_counter()
    try:
        result = await provider.check_grammar(prompt)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            analysis = analyse(prompt, result.correction)
        except Exception:
            # Observation only. A fault in it must not reach the except below
            # and turn a perfectly good verdict into an error result.
            analysis = {}
        fields = {
            "has_issues": result.has_issues,
            "explanation": result.explanation,
            "status": "issues" if result.has_issues else "clean",
            "types": result.types,
            "issues": result.issues,
            "correction": result.correction,
            "diff": analysis.get("diff", []),
        }
        debug = {
            "request": request_meta,
            "raw": result.raw,
            "derived": {"dropped_issues": result.dropped_issues},
            "timing": {"latency_ms": elapsed_ms, "usage": result.usage},
            "analysis": analysis,
        }
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        fields = {
            "has_issues": False,
            "explanation": f"Grammar check failed: {e}",
            "status": "error",
            "types": [],
            "issues": [],
            "correction": "",
            "diff": [],
        }
        # A failure previously left only the formatted message. The type is
        # what tells a timeout apart from a schema rejection.
        debug = {
            "request": request_meta,
            "error": {"type": type(e).__name__, "message": str(e)},
            "timing": {"latency_ms": elapsed_ms},
        }
    return fields, debug


async def _run_check(
    store: ResultStore,
    provider,
    username: str,
    prompt: str,
    project: str = "",
    agent: str = "",
    *,
    checker: str = "",
    provider_name: str = "",
    model: str = "",
):
    request_meta = {
        "checker": checker,
        "provider": provider_name,
        "model": model,
        "system_prompt_hash": SYSTEM_PROMPT_HASH,
    }
    fields, debug = await _perform_check(provider, prompt, request_meta)
    await store.add_and_broadcast(
        CheckResult(
            username=username, prompt=prompt, project=project, agent=agent,
            checker=checker, debug=debug, **fields,
        )
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    username = websocket.app.state.auth.validate(token)
    if not username:
        await websocket.close(code=4401, reason="unauthorized")
        return
    await websocket.accept()
    websocket.app.state.store.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket.app.state.store.disconnect(websocket)
