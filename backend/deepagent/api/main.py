from __future__ import annotations

import time
import uuid

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from deepagent.api.sessions import SessionStore
from deepagent.common.config import get_settings, resolve_path
from deepagent.common.logger import get_logger, request_id_ctx, source_ctx
from deepagent.common.schemas import (
    ChatRequest,
    ChatResponse,
    MemoryWriteRequest,
    TodoWriteRequest,
)
from deepagent.core.agent import DeepAgent
from deepagent.core.memory import create_store, store_put, store_search
from deepagent.core.todos import TodoStore

settings = get_settings()
logger = get_logger("deepagent.api")
app = FastAPI(title="DeepAgent")

@app.middleware("http")
async def log_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())
    request_id_ctx.set(req_id)
    
    # Set source context
    token = source_ctx.set({
        "module": "deepagent.api",
        "endpoint": request.url.path,
        "method": request.method
    })
    
    start_time = time.time()
    logger.info(f"Incoming Request: {request.method} {request.url.path} Query={request.query_params}")

    # Capture and log request body for chat endpoint (useful for debugging user input)
    if request.url.path == "/api/chat" and request.method == "POST":
        try:
            body_bytes = await request.body()
            # Restore body for downstream processing
            # FastAPI/Starlette consumes body stream, so we need to create a new receive function
            async def new_receive():
                return {"type": "http.request", "body": body_bytes}
            request._receive = new_receive
            
            body_str = body_bytes.decode("utf-8")
            logger.debug(f"Request Body: {body_str}")
        except Exception:
            logger.warn("Failed to read request body")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        logger.info(
            f"Outgoing Response: {response.status_code} "
            f"Duration={process_time:.2f}ms"
        )
        return response
    except Exception as e:
        logger.error(f"Request Failed: {str(e)}", exc_info=True)
        raise e
    finally:
        source_ctx.reset(token)

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
def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    thread_id = req.thread_id or agent.new_thread_id()
    session_store.add(req.user_id, thread_id)
    logger.debug("chat request", extra={"thread_id": thread_id, "user_id": req.user_id})
    result = agent.invoke(thread_id, req.user_id, req.message, background_tasks=background_tasks)
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
