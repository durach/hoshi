import asyncio
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from auth import TokenAuth
from config import Settings
from providers import create_provider
from store import CheckResult, ResultStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.background_tasks = set()
    app.state.store = ResultStore()
    app.state.auth = TokenAuth(settings.tokens_file)
    app.state.provider = create_provider(
        settings.provider,
        settings.model,
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        gemini_api_key=settings.gemini_api_key,
    )
    yield


app = FastAPI(title="Hoshi", lifespan=lifespan)


class CheckRequest(BaseModel):
    prompt: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/check", status_code=202)
async def check(
    request: Request,
    body: CheckRequest,
    authorization: str = Header(default=""),
):
    token = authorization.removeprefix("Bearer ").strip()
    username = request.app.state.auth.validate(token)
    if not username:
        raise HTTPException(status_code=401, detail="unauthorized")

    task = asyncio.create_task(
        _run_check(
            request.app.state.store, request.app.state.provider, username, body.prompt
        )
    )
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return {"status": "accepted"}


async def _run_check(store: ResultStore, provider, username: str, prompt: str):
    try:
        result = await provider.check_grammar(prompt)
        check_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=result.has_issues,
            explanation=result.explanation,
        )
        await store.add_and_broadcast(check_result)
    except Exception as e:
        error_result = CheckResult(
            username=username,
            prompt=prompt,
            has_issues=False,
            explanation=f"Grammar check failed: {e}",
            status="error",
        )
        await store.add_and_broadcast(error_result)


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
