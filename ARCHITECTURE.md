# DeepAgent Architecture

This document provides a comprehensive overview of the DeepAgent system architecture, designed for modularity, scalability, and robust agentic workflows.

## 1. High-Level Architecture

DeepAgent follows a layered architecture pattern, strictly separating API concerns from core business logic and external integrations.

```mermaid
graph TD
    subgraph FrontendLayer ["Frontend Layer"]
        UI["React + Vite UI"]
    end

    subgraph BackendLayer ["Backend Layer (Python)"]
        API["API Gateway (FastAPI)"]
        
        subgraph CoreDomain ["Core Domain"]
            Agent["DeepAgent Core"]
            Plan["Planner & Reasoner"]
            Mem["Memory System"]
        end
        
        subgraph Infrastructure ["Infrastructure"]
            Router["Model Router"]
            Tools["ToolBox"]
        end
    end

    subgraph ExternalWorld ["External World"]
        LLM["LLM Providers (Zhipu/OpenAI)"]
        MCP["MCP Servers"]
        Skills["Skill Endpoints"]
        FS["File System"]
    end

    UI <--> |JSON/REST| API
    API <--> Agent
    Agent --> Plan
    Agent --> Mem
    Agent --> Tools
    Agent --> Router
    Router --> LLM
    Tools --> MCP
    Tools --> Skills
    Tools --> FS
```

## 2. Core Module Design

The `core` module is the heart of the application, enforcing the Single Responsibility Principle (SRP).

### Directory Structure
- `deepagent.core.agent`: Main orchestration logic and state management.
- `deepagent.core.memory`: Long-term persistent memory and vector search.
- `deepagent.core.models`: LLM adapter layer and routing logic.
- `deepagent.core.todos`: Task tracking and persistence.
- `deepagent.core.toolbox`: Tool registration, MCP client integration, and subagent delegation.

### Class Relationship Diagram
```mermaid
classDiagram
    %% 核心类定义（保留所有方法/属性，仅修正语法）
    class DeepAgent {
        +invoke(message)
        +plan(message)
        -_run_subagent(task)
    }

    class ModelRouter {
        +get_model(step)
        +specs: object
    }

    class ToolBox {
        +tools()
        +mcp_registry
        +skill_registry
    }

    class MemoryStore {
        +search(query)
        +put(key, value)
    }

    class TodoStore {
        +get(threadId)
        +write(threadId, items)
    }

    %% 补充缺失的引用类（关键修复）
    class MCPRegistry { }
    class SkillRegistry { }

    %% 规范连接语法（统一空格+转义空格说明）
    DeepAgent *-- ModelRouter : uses
    DeepAgent *-- ToolBox : uses
    DeepAgent *-- MemoryStore : persists\ state
    DeepAgent *-- TodoStore : tracks\ tasks 
    ToolBox o-- MCPRegistry : integrates
    ToolBox o-- SkillRegistry : integrates
```

## 3. Data Flow & Execution Pipeline

When a user sends a message, DeepAgent executes a structured cognitive cycle:

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant API as API Layer
    participant Agent as DeepAgent Core
    participant Plan as Planner
    participant Mem as Memory/Todos
    participant LLM as Model Router
    participant Tools as ToolBox

    User->>API: POST /api/chat (message)
    API->>Agent: invoke(thread_id, message)
    
    rect rgb(240, 248, 255)
        Note over Agent, Mem: 1. Context Construction
        Agent->>Mem: Load History & Todos
        Agent->>Mem: Search Relevant Memories
        Mem-->>Agent: Context Data
    end

    rect rgb(255, 250, 240)
        Note over Agent, Plan: 2. Planning
        Agent->>Plan: Generate/Update Plan
        Plan->>LLM: Call Planner Model
        LLM-->>Plan: Structured Plan
        Plan-->>Agent: Updated Plan & Todos
        Agent->>Mem: Persist Initial Todos
    end

    rect rgb(240, 255, 240)
        Note over Agent, Tools: 3. Execution (LangGraph Loop)
        loop Until Goal Met
            Agent->>LLM: Call Chat Model (Reasoning)
            LLM-->>Agent: Tool Call / Final Answer
            
            opt Tool Execution
                Agent->>Tools: Execute Tool (MCP/Skill/FS)
                Tools-->>Agent: Tool Result
            end
        end
    end

    rect rgb(255, 240, 245)
        Note over Agent, Mem: 4. Reflection & Storage
        Agent->>Mem: Store New Facts (Memory)
        opt Summarization
            Agent->>LLM: Summarize Conversation
            LLM-->>Agent: Summary
        end
    end

    Agent-->>API: ChatResponse (answer, plan, memories)
    API-->>User: JSON Response
```

1.  **Context Construction**:
    *   Retrieves recent conversation history.
    *   Searches long-term memory for relevant facts.
    *   Loads current Todo list state.
2.  **Planning (Reasoning)**:
    *   Uses the `planner` model to analyze the request.
    *   Generates or updates the `Plan` and `TodoItems`.
3.  **Execution**:
    *   The LangGraph-based engine executes tools defined in the plan.
    *   Supports recursive sub-agent spawning for complex sub-tasks.
4.  **Reflection & Storage**:
    *   Summarizes the interaction if the conversation turn limit is reached.
    *   Stores new facts into `MemoryStore`.
    *   Updates `TodoStore` with task completion status.
5.  **Response**:
    *   Returns the final answer along with the updated plan, todos, and relevant memories to the client.

## 4. Key Technical Decisions

*   **LangGraph Foundation**: Uses LangGraph for stateful, cyclic agent workflows, allowing for retries, human-in-the-loop (future), and complex branching.
*   **Model Agnostic**: The `ModelRouter` decouples the system from specific providers. Configuration allows swapping models (e.g., Zhipu vs OpenAI) for different pipeline steps (Chat vs Plan vs Summary) without code changes.
*   **Protocol Oriented**: First-class support for the Model Context Protocol (MCP), enabling standard integration with external tools and data sources.
*   **Recursive Agents**: The architecture supports "fractal" scaling, where an agent can spawn a child agent (with its own isolated context and tools) to solve a sub-problem, returning only the final result to the parent.

## 5. Memory System Design

The memory system is designed to provide both immediate context awareness and long-term continuity, preventing the "amnesia" typical of stateless LLM interactions.

### Architecture

```mermaid
graph TD
    subgraph RuntimeContext ["Runtime Context"]
        Prompt[System Prompt]
        History[Recent History N turns]
        Facts[Retrieved Facts Summaries]
    end

    subgraph StorageLayer ["Storage Layer"]
        JSON[(Long-Term Store JSON File)]
        SQLite[(Graph State SQLite DB)]
    end

    subgraph Processes ["Processes"]
        Search[Keyword Semantic Search]
        Summarizer[Auto-Summarizer]
        Checkpointer[State Checkpointer]
    end

    Agent[DeepAgent] --> Read1 --> Search
    Search --> Query --> JSON
    Search --> Inject --> Facts
    
    Agent --> Read2 --> History
    History --> From --> JSON
    
    Agent --> Write --> JSON
    Agent --> Checkpoint --> Checkpointer
    Checkpointer --> Persist --> SQLite
    
    JSON --> Trigger --> Summarizer
    Summarizer --> WriteSum --> JSON

    %% Define invisible helper nodes for labels (avoids long connector text)
    Read1[Read]
    Read2[Read]
    Query[Query]
    Inject[Inject]
    From[From]
    Write[Write Turn]
    Checkpoint[Checkpoint]
    Persist[Persist]
    Trigger[Trigger every 8 turns]
    WriteSum[Write Summary]
    
    %% Style helper nodes to be invisible (optional, for clean look)
    classDef invisible fill:none,stroke:none,font-size:0;
    class Read1,Read2,Query,Inject,From,Write,Checkpoint,Persist,Trigger,WriteSum invisible;
```

### Key Components

1.  **Long-Term Persistence (`MemoryStore`)**:
    *   **Mechanism**: A file-backed key-value store (JSON) that persists across server restarts.
    *   **Content**: Stores raw conversation turns (`type: conversation`) and high-level summaries (`type: summary`).
    *   **Retrieval**: Uses a hybrid approach combining:
        *   **Recency**: Always fetching the most recent N turns for immediate context.
        *   **Relevance**: Keyword-based scoring to find related past interactions based on the current user query.

2.  **Automatic Summarization**:
    *   **Trigger**: Runs as a background task every 8 conversation turns.
    *   **Function**: Compresses older dialogue into concise summaries, preserving key decisions and facts while freeing up context window space.
    *   **Usage**: The latest summary is always injected into the system prompt.

3.  **Graph State (`Checkpointer`)**:
    *   **Technology**: `SqliteSaver` (SQLite).
    *   **Purpose**: Persists the exact state of the LangGraph execution (nodes, variables, tool outputs). This allows the agent to pause, resume, or retry complex workflows seamlessly.

4.  **Context Assembly**:
    Before generating a response, the agent constructs a dynamic prompt containing:
    *   **System Instructions**: Core identity and rules.
    *   **Relevant Memories**: Facts retrieved via search.
    *   **Global Summary**: The latest condensed view of the conversation.
    *   **Recent History**: Raw dialogue from the last few turns.
