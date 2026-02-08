# DeepAgent

DeepAgent is a LangChain DeepAgents-style system built on LangGraph. It ships a Python backend with planning, task decomposition, tool execution, subagent spawning, and long-term memory, plus a React-based UI. It supports MCP and custom skill endpoints via configurable registries.

## Highlights

- Planning and task decomposition with a `write_todos` tool
- Context management tools for filesystem access
- Subagent spawning for isolated deep work
- Persistent memory across sessions
- MCP and skill protocol integrations
- Single-port production serve or split deployments

## Requirements

- Python 3.10+
- Node.js 18+

## One-click install

- Windows: run `install.bat`
- Linux/macOS: run `./install.sh`

These scripts install backend and frontend dependencies and are resilient to future dependency changes.

## Configuration

Copy `backend/.env.example` to `backend/.env` and set your Zhipu key.

Required:

- `ZHIPU_API_KEY`

Optional:

- `DEEPAGENT_ENV`: `dev` or `prod`
- `DEEPAGENT_HOST`, `DEEPAGENT_PORT`
- `DEEPAGENT_FRONTEND_DEV_SERVER`
- `DEEPAGENT_MEMORY_DB`
- `DEEPAGENT_MEMORY_STORE`
- `DEEPAGENT_MCP_SERVERS`: JSON array of `{ "name": "...", "endpoint": "..." }`
- `DEEPAGENT_SKILLS`: JSON array of `{ "name": "...", "endpoint": "..." }`

## Run (dev)

Backend:

```
cd backend
python -m deepagent.cli start --mode debug
```

Frontend:

```
cd frontend
npm run dev
```

Open http://localhost:5173
 
Debug flags:
- VSCode compound launch sets DEEPAGENT_DEBUG=1 and VITE_DEBUG=true
- You can also run `./start.sh --debug` or `start.bat --debug`

## Run (production, single port)

```
cd frontend
npm run build
cd ../backend
python -m deepagent.cli start --mode prod --detach
```

Open http://localhost:8000
 
One-click start:
```
./start.sh
```
or on Windows
```
start.bat
```

Stop server:

```
cd backend
python -m deepagent.cli stop
```

## Architecture

- `backend/deepagent/agent.py`: DeepAgents orchestration and planning
- `backend/deepagent/toolbox.py`: tools for todos, filesystem, memory, MCP, skills, subagents
- `backend/deepagent/memory.py`: persistent memory (SQLite checkpointer + JSON store)
- `backend/deepagent/main.py`: FastAPI API and frontend mounting
- `frontend/`: Vite + React + MUI UI
 
Logging:
- Backend logger respects `DEEPAGENT_DEBUG` and emits detailed traces in debug
- Frontend logger respects `VITE_DEBUG` and emits debug-level diagnostics

## API

- `POST /api/chat`: main conversation endpoint
- `GET /api/todos`, `POST /api/todos`: read/write todos
- `GET /api/memory`, `POST /api/memory`: read/write long-term memory

## Notes

No paid cloud services are required. The default model is `glm-4-flash` via Zhipu.
