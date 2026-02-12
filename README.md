# DeepAgent

DeepAgent is an enterprise-grade, autonomous AI system built on LangGraph. It features a modular Python backend capable of systematic planning, task decomposition, recursive sub-agent spawning, and persistent long-term memory. It comes with a modern React-based frontend and full support for the Model Context Protocol (MCP).

## 🚀 Key Features

- **Autonomous Planning**: Decomposes complex user requests into actionable Todo lists using a dedicated planner model.
- **Persistent Memory**: Remembers user preferences and facts across sessions using vector search and structured storage.
- **Recursive Sub-Agents**: Spawns isolated child agents to handle complex sub-tasks without cluttering the main context.
- **Tool Ecosystem**: Native support for Model Context Protocol (MCP) servers and custom Skill endpoints.
- **Production Ready**: Layered architecture, strictly typed (mypy), and modular design.

## 🏗️ Architecture

The system is built on a clean, layered architecture separating API concerns from core business logic.

- **Core Logic**: `backend/deepagent/core/` (Agent, Memory, Models)
- **API Layer**: `backend/deepagent/api/` (FastAPI endpoints)
- **Integrations**: `backend/deepagent/integrations/` (MCP, Skills)

👉 **[View Detailed Architecture & Design Diagrams](ARCHITECTURE.md)**

## 🛠️ Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18 or higher
- **API Key**: A Zhipu AI API key (or OpenAI compatible key)

## ⚡ Quick Start

### 1. Installation

**Windows**:
```cmd
install.bat
```

**Linux/macOS**:
```bash
./install.sh
```

### 2. Configuration

Create a `.env` file in the `backend/` directory:

```ini
ZHIPU_API_KEY=your_key_here
DEEPAGENT_ENV=dev
DEEPAGENT_LOG_LEVEL=info
```

### 3. Run Application

**Windows**:
```cmd
start.bat --debug
```

**Linux/macOS**:
```bash
./start.sh --debug
```

This will launch:
- Backend API at `http://localhost:8000`
- Frontend UI at `http://localhost:5173`

## 📦 Production Build

To run in production mode (single optimized artifact):

```bash
# Windows
start.bat

# Linux/Mac
./start.sh
```

## 🔌 API Endpoints

- `POST /api/chat`: Main conversation endpoint (supports planning & execution).
- `GET /api/todos`: Retrieve current task list.
- `GET /api/memory`: Access long-term memory store.
- `GET /api/sessions`: List active conversation threads.

## 🧩 Configuration & Models

DeepAgent uses a `config/models.yaml` to define model behaviors. You can swap providers (Zhipu, OpenAI, etc.) for different steps of the cognitive pipeline:

```yaml
defaults:
  provider: zhipu
  model: glm-4-flash

models:
  plan:
    temperature: 0.1
  summary:
    model: glm-4-flash
```

## 📄 License

MIT
