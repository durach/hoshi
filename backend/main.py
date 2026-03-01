import asyncio

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from auth import TokenAuth
from config import Settings
from providers import create_provider
from store import CheckResult, ResultStore

_background_tasks: set[asyncio.Task] = set()

settings = Settings()
app = FastAPI(title="Hoshi")
store = ResultStore()
auth = TokenAuth(settings.tokens_file)
provider = create_provider(
    settings.provider,
    settings.model,
    anthropic_api_key=settings.anthropic_api_key,
    openai_api_key=settings.openai_api_key,
    gemini_api_key=settings.gemini_api_key,
)


class CheckRequest(BaseModel):
    prompt: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/check", status_code=202)
async def check(
    body: CheckRequest,
    authorization: str = Header(default=""),
):
    token = authorization.removeprefix("Bearer ").strip()
    username = auth.validate(token)
    if not username:
        raise HTTPException(status_code=401, detail="unauthorized")

    task = asyncio.create_task(_run_check(username, body.prompt))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "accepted"}


async def _run_check(username: str, prompt: str):
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
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    store.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        store.disconnect(websocket)
