from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .agent import DeepAgent
from .config import get_settings, resolve_path
from .memory import store_put, store_search, create_store
from .logger import get_logger
from .schemas import ChatRequest, ChatResponse, MemoryWriteRequest, TodoWriteRequest
from .sessions import SessionStore
from .todos import TodoStore


settings = get_settings()
logger = get_logger("deepagent.api")
app = FastAPI(title="DeepAgent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

todo_store = TodoStore()
memory_store = create_store()
agent = DeepAgent(todo_store=todo_store, store=memory_store)
session_store = SessionStore()


@app.get("/api/health")
def health():
    logger.debug("health check")
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    thread_id = req.thread_id or agent.new_thread_id()
    session_store.add(req.user_id, thread_id)
    logger.debug("chat request", extra={"thread_id": thread_id, "user_id": req.user_id})
    result = agent.invoke(thread_id, req.user_id, req.message)
    return ChatResponse(
        thread_id=thread_id,
        user_id=req.user_id,
        reply=result["reply"],
        plan=result["plan"],
        todos=result["todos"],
        memories=result["memories"],
    )


@app.post("/api/todos")
def write_todos(req: TodoWriteRequest):
    saved = todo_store.write(req.thread_id, req.todos)
    return [t.model_dump() for t in saved]


@app.get("/api/todos")
def get_todos(thread_id: str):
    return [t.model_dump() for t in todo_store.get(thread_id)]


@app.get("/api/sessions")
def list_sessions(user_id: str):
    return session_store.list(user_id)


@app.post("/api/memory")
def memory_put(req: MemoryWriteRequest):
    return {"id": store_put(memory_store, req.user_id, req.value)}


@app.get("/api/memory")
def memory_search(user_id: str, query: str | None = None, limit: int = 5):
    results = store_search(memory_store, user_id, query=query, limit=limit)
    return [r.dict() for r in results]


def _mount_frontend(app: FastAPI) -> None:
    dist_path = resolve_path(settings.frontend_dist)
    if dist_path.exists():
        app.mount("/", StaticFiles(directory=dist_path, html=True), name="frontend")
        return

    dev_server = settings.frontend_dev_server
    html = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>DeepAgent</title>
      </head>
      <body>
        <div id="root"></div>
        <script type="module" src="{dev_server}/src/main.tsx"></script>
      </body>
    </html>
    """

    @app.get("/", response_class=HTMLResponse)
    def dev_index():
        return HTMLResponse(html)


_mount_frontend(app)
