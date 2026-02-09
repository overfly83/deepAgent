from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools import tool

from deepagent.core.memory import store_put, store_search
from deepagent.core.todos import TodoStore


class ToolBox:
    def __init__(
        self,
        todo_store: TodoStore,
        memory_store,
        mcp_registry,
        skill_registry,
        subagent_fn: Callable[[str], str],
    ) -> None:
        self.todo_store = todo_store
        self.memory_store = memory_store
        self.mcp_registry = mcp_registry
        self.skill_registry = skill_registry
        self.subagent_fn = subagent_fn

    def tools(self):
        @tool("spawn_subagent")
        def spawn_subagent(task: str) -> str:
            """Spawn a subagent to handle a focused task."""
            return self.subagent_fn(task)

        @tool("memory_put")
        def memory_put(user_id: str, value: dict[str, Any]) -> str:
            """Persist a memory item for a user."""
            return store_put(self.memory_store, user_id, value)

        @tool("memory_search")
        def memory_search(user_id: str, query: str | None = None, limit: int = 5):
            """Search memories for a user."""
            memories = store_search(self.memory_store, user_id, query=query, limit=limit)
            return [m.dict() for m in memories]

        @tool("mcp_call")
        def mcp_call(server_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Call a configured MCP server endpoint."""
            import httpx
            server = self.mcp_registry.servers.get(server_name)
            if not server:
                raise ValueError(f"MCP server not found: {server_name}")
            with httpx.Client(timeout=30) as client:
                res = client.post(server.endpoint, json=payload)
                res.raise_for_status()
                return res.json()

        @tool("skill_call")
        def skill_call(skill_name: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Call a configured skill endpoint."""
            import httpx
            skill = self.skill_registry.skills.get(skill_name)
            if not skill:
                raise ValueError(f"Skill not found: {skill_name}")
            with httpx.Client(timeout=30) as client:
                res = client.post(skill.endpoint, json=payload)
                res.raise_for_status()
                return res.json()

        return [
            spawn_subagent,
            memory_put,
            memory_search,
            mcp_call,
            skill_call,
        ]
