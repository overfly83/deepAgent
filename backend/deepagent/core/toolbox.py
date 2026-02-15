from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any, Callable

from langchain_core.tools import tool

from deepagent.core.memory import store_put, store_search
from deepagent.core.todos import TodoStore


from deepagent.common.logger import get_logger

logger = get_logger("deepagent.core.toolbox")

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
        self._mcp_init_lock = threading.Lock()

    def _run_async(self, coro):
        import inspect
        
        # If the object is not awaitable (e.g. it's already a result), return it directly
        if not inspect.isawaitable(coro):
            return coro
            
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            # When running inside an existing loop (like FastAPI), we cannot use asyncio.run()
            # We must use run_coroutine_threadsafe or similar, BUT since this is a synchronous method 
            # called by a synchronous tool, we need to block until the coroutine finishes.
            
            # Creating a new thread to run a new loop is one way to bridge sync-to-async
            future = concurrent.futures.Future()
            
            def run_in_new_loop():
                try:
                    result = asyncio.run(coro)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
            
            # We use a ThreadPoolExecutor to run the async code in a separate thread 
            # which has its own event loop via asyncio.run
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(run_in_new_loop)
                return future.result()
        else:
            return asyncio.run(coro)

    def _ensure_mcp_initialized(self):
        with self._mcp_init_lock:
            if not self.mcp_registry._initialized:
                # mcp_registry.initialize() is synchronous, so call it directly
                self.mcp_registry.initialize()

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
        def mcp_call(server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            """Call a tool on a configured MCP server.
            
            Args:
                server_name: Name of the MCP server (e.g., 'stock-mcp')
                tool_name: Name of the tool to call (e.g., 'get_quote')
                arguments: Arguments to pass to the tool
            
            Returns:
                The result from the MCP server tool
            """
            logger.info(f"Calling MCP tool '{tool_name}' on server '{server_name}' with args: {arguments}")
            self._ensure_mcp_initialized()
            
            payload = {
                "name": tool_name,
                "arguments": arguments
            }
            
            try:
                result = self._run_async(self.mcp_registry.call(server_name, payload))
                logger.info(f"MCP tool '{tool_name}' returned: {str(result)[:200]}...") # Truncate for log cleanliness
                return result
            except Exception as e:
                logger.error(f"MCP tool '{tool_name}' failed: {e}", exc_info=True)
                raise e

        @tool("mcp_list_tools")
        def mcp_list_tools(server_name: str) -> list[dict]:
            """List available tools on a configured MCP server.
            
            Args:
                server_name: Name of the MCP server (e.g., 'stock-mcp')
            
            Returns:
                List of available tools with their names and descriptions
            """
            self._ensure_mcp_initialized()
            
            return self._run_async(self.mcp_registry.list_tools(server_name))

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
            mcp_list_tools,
            skill_call,
        ]