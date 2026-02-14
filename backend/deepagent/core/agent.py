from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from datetime import datetime
from threading import get_ident
from typing import Any, cast

import httpx
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel as LCBaseModel
from pydantic import field_validator

from deepagent.common.config import get_settings, resolve_path
from deepagent.common.logger import get_logger
from deepagent.common.schemas import TodoItem
from deepagent.core.memory import (
    create_checkpointer,
    create_store,
    store_all,
    store_put,
    store_search,
)
from deepagent.core.models import ModelRouter
from deepagent.core.todos import TodoStore
from deepagent.core.toolbox import ToolBox
from deepagent.integrations.mcp_client import MCPRegistry
from deepagent.integrations.skills import SkillRegistry

logger = get_logger("deepagent.core.agent")

class PlanOutput(LCBaseModel):
    plan: list[str] = []
    todos: list[TodoItem] = []
    summary: str = ""

    @field_validator("plan", mode="before")
    def parse_plan(cls, v):
        if isinstance(v, str):
            return [v]
        return v
        
    @field_validator("todos", mode="before")
    def parse_todos(cls, v):
        if not isinstance(v, list):
            return []
        for item in v:
            if isinstance(item, dict):
                if "id" not in item:
                    item["id"] = str(uuid.uuid4())
                if "status" not in item:
                    item["status"] = "pending"
        return v


class DeepAgent:
    def __init__(
        self,
        depth: int = 0,
        todo_store: TodoStore | None = None,
        store=None,
        checkpointer=None,
    ) -> None:
        self.settings = get_settings()
        self.todo_store = todo_store or TodoStore()
        self.store = store or create_store()
        self.checkpointer = checkpointer
        
        mcp_config_path = resolve_path(self.settings.mcp_config_path)
        mcp_servers_dir = str(resolve_path(self.settings.mcp_servers_dir))
        if mcp_config_path.exists():
            self.mcp_registry = MCPRegistry.from_config(str(mcp_config_path), mcp_servers_dir)
        else:
            self.mcp_registry = MCPRegistry.from_env(os.getenv("DEEPAGENT_MCP_SERVERS"))
        
        self.skill_registry = SkillRegistry.from_env(os.getenv("DEEPAGENT_SKILLS"))
        self.depth = depth
        self._agent_cache: dict[tuple[str, int], Any] = {}
        
        # Concurrency limit semaphore
        self._concurrency_semaphore = asyncio.Semaphore(self.settings.max_concurrency)

        self.model_router = ModelRouter.from_config(
            self.settings.model_config_path, self.settings
        )
        self.chat_model = self.model_router.get_model("chat")
        self.planner_model = self.model_router.get_model("plan")
        self.planner = self.planner_model.with_structured_output(PlanOutput)

        self.toolbox = ToolBox(
            todo_store=self.todo_store,
            memory_store=self.store,
            mcp_registry=self.mcp_registry,
            skill_registry=self.skill_registry,
            subagent_fn=self._run_subagent,
        )

    def _call_with_retry(self, fn):
        delay = 1.0
        for _ in range(3):
            try:
                return fn()
            except httpx.HTTPStatusError as exc:
                if exc.response is None or exc.response.status_code != 429:
                    raise
                time.sleep(delay + random.uniform(0, 0.3))
                delay *= 2
        return None

    def _summarize_text(self, turns: list[dict[str, str]]) -> str:
        if not turns:
            return ""
        lines = []
        for turn in turns:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        if not lines:
            return ""
        system = SystemMessage(
            content=(
                "Summarize the conversation for long-term memory. Keep key facts, goals,"
                " preferences, decisions, and open questions. Be concise."
            )
        )
        summary_model = self.model_router.get_model("summary")
        result = self._call_with_retry(
            lambda: summary_model.invoke([system, HumanMessage(content="\n".join(lines))])
        )
        return str(result.content) if result else ""

    def _maybe_store_summary(
        self,
        user_id: str,
        thread_id: str,
        items: list[dict[str, Any]],
        conversations: list[dict[str, Any]],
    ) -> None:
        if len(conversations) < 8:
            return
        last_summary_count = 0
        for item in reversed(items):
            value = item.get("value") if isinstance(item, dict) else None
            if isinstance(value, dict) and value.get("type") == "summary":
                last_summary_count = int(value.get("conversation_count", 0))
                break
        if len(conversations) - last_summary_count < 8:
            return
        start = last_summary_count if last_summary_count >= 0 else 0
        chunk = conversations[start:]
        turns: list[dict[str, str]] = []
        for value in chunk:
            um = value.get("user_message")
            ar = value.get("agent_reply")
            if isinstance(um, str) and um:
                turns.append({"role": "user", "content": um})
            if isinstance(ar, str) and ar:
                turns.append({"role": "assistant", "content": ar})
        summary = self._summarize_text(turns)
        if not summary:
            return
        store_put(
            self.store,
            user_id,
            {
                "type": "summary",
                "thread_id": thread_id,
                "conversation_count": len(conversations),
                "summary": summary,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
    def _get_agent(self, thread_id: str):
        cache_key = (thread_id, get_ident())
        if cache_key in self._agent_cache:
            return self._agent_cache[cache_key]
        checkpointer = create_checkpointer(thread_id)
        
        # Configure recursion limit
        agent = create_deep_agent(
            model=self.chat_model,
            tools=self.toolbox.tools(),
            checkpointer=checkpointer,
            store=self.store,
            system_prompt=self._system_prompt(),
            backend=FilesystemBackend(root_dir=str(resolve_path(self.settings.workspace_root))),
        )
        # Note: LangGraph agents are compiled. If we could pass recursion_limit here we would.
        # But usually it's passed at invoke time via config.
        
        self._agent_cache[cache_key] = agent
        return agent

    def new_thread_id(self) -> str:
        return str(uuid.uuid4())

    def _system_prompt(self) -> str:
        # Dynamically list available tools
        mcp_tools_desc = ""
        try:
            self.toolbox._ensure_mcp_initialized()
            all_mcp_tools = []
            for server_name in self.mcp_registry.servers:
                # Note: list_tools is synchronous, no need for _run_async
                # If we make it async later, we'd need _run_async
                tools = self.mcp_registry.list_tools(server_name)
                for t in tools:
                     all_mcp_tools.append(f"- {t['name']} (Server: {server_name}): {t['description']}")
            if all_mcp_tools:
                mcp_tools_desc = "\nAvailable MCP Tools:\n" + "\n".join(all_mcp_tools)
        except Exception as e:
            logger.warn(f"Failed to list MCP tools for system prompt: {e}")

        return f"""
            You are DeepAgent, a structured, context-aware assistant designed to handle tasks efficiently through systematic planning, context management, specialized subagent collaboration, and persistent long-term memory. Adhere strictly to the following guidelines, integrating all core capabilities into your workflow:
            
            {mcp_tools_desc}

            1. Core Identity & Fundamental Requirements: Always act as DeepAgent. For every task—whether simple or complex—first decompose it into a clear, concise short plan (1-5 discrete, actionable steps), and consistently maintain and update your task list using the built-in write_todos tool. Prioritize recalling user history across all sessions, extract durable, relevant facts from interactions, and store them permanently using the memory_put tool to ensure continuity and avoid redundant work.
            
            2. Planning and Task Decomposition (via write_todos): Leverage the built-in write_todos tool as the foundation of your workflow. Break down complex tasks into small, manageable, discrete steps that can be executed sequentially or in parallel (as needed). Track progress on each todo item in real time—mark steps as completed once finished, update steps if new information emerges or requirements change, and remove irrelevant steps to keep the task list focused. Ensure each todo is specific (e.g., "Read the config file to extract API keys" instead of "Handle config") and aligned with the overall task goal.
            
            3. Context Management (via File System Tools): Utilize the provided file system tools (ls, read_file, write_file, edit_file) proactively to manage context efficiently. Offload large chunks of context (e.g., long documents, detailed logs, complex data structures) to in-memory or filesystem storage instead of keeping them in the prompt window—this prevents context overflow and ensures you can work seamlessly with variable-length tool results. When working with files: use ls to explore the file structure first, read_file to access content only when needed, write_file to save intermediate results or persistent data, and edit_file to modify existing content incrementally. Always reference stored file paths in your todos and plans for easy retrieval.
            
            4. Subagent Spawning (via Task Tool): Use the built-in task tool to spawn specialized subagents when appropriate, focusing on context isolation. Deploy subagents for narrow, deep subtasks (e.g., "Validate type annotations with mypy", "Summarize the user’s previous session history") that would clutter the main agent’s context or require specialized expertise. Keep the main agent’s context clean by delegating these subtasks to subagents, and ensure subagents return clear, actionable results that the main agent can integrate into its overall plan. Track subagent progress via write_todos and retrieve their outputs promptly to maintain workflow continuity.
            
            5. Long-Term Memory (via LangGraph's Memory Store): Extend your capabilities with persistent memory across all threads using LangGraph's Memory Store. Use memory_put to save durable facts (e.g., user preferences, key project details, previously confirmed conclusions, API credentials) from each conversation—avoid storing temporary or irrelevant information (e.g., intermediate todo updates, failed tool outputs). Before starting a new task or responding to a user query, recall relevant user history and stored facts to ensure consistency across sessions. If a fact is unclear or missing, use your tools to verify or request clarification, then update the memory store accordingly.
            
            6. External Tools (MCP/Skills): You have access to external tools via the 'mcp_call' and 'skill_call' functions. 
               - To use an MCP tool, call 'mcp_call' with the server_name, tool_name, and arguments. 
               - CHECK the 'Available MCP Tools' list above to see what is available.
               - If the user asks for financial data, stock prices, or other domain-specific info, CHECK if an MCP tool exists for it (e.g. 'get_stock_price' on 'finance' server).

            Overarching Rule: Prioritize clarity, consistency, and adaptability. Your plan and todos should evolve as new information emerges, your context should remain lean and organized via file tools, subagents should handle specialized work to keep you focused, and long-term memory should eliminate redundancy and ensure continuity across all user interactions.
        """

    def _run_subagent(self, task: str) -> str:
        if self.depth >= 1:
            return "Subagent limit reached"
        subagent = DeepAgent(
            depth=self.depth + 1,
            todo_store=self.todo_store,
            store=self.store,
            checkpointer=None,
        )
        sub_thread = f"sub-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": sub_thread, "user_id": "subagent"}}
        result = subagent._get_agent(sub_thread).invoke(
            {"messages": [{"role": "user", "content": task}]},
            config=config,
        )
        last = result["messages"][-1].content if result.get("messages") else ""
        return str(last)

    def plan(self, message: str) -> PlanOutput:
        # Include available tools in planning context to help planner know what's possible
        mcp_tools_desc = ""
        try:
            self.toolbox._ensure_mcp_initialized()
            all_mcp_tools = []
            for server_name in self.mcp_registry.servers:
                tools = self.mcp_registry.list_tools(server_name)
                for t in tools:
                     all_mcp_tools.append(f"- {t['name']} (Server: {server_name}): {t['description']}")
            if all_mcp_tools:
                mcp_tools_desc = "\nAvailable Tools for Execution:\n" + "\n".join(all_mcp_tools)
        except Exception:
            pass

        system = SystemMessage(
            content=(
                "You are a planning assistant. Analyze the user's request and produce a structured plan.\n"
                f"{mcp_tools_desc}\n"
                "Return a JSON object with:\n"
                "- 'plan': A list of high-level steps (strings). If only one step, return a list with one string.\n"
                "- 'todos': A list of actionable items, each with a 'title' and a unique 'id' (string).\n"
                "- 'summary': A brief summary of the intent.\n"
                "If the user asks for information that can be retrieved via available tools (e.g. stock prices), create a plan step to use that tool."
                "Do NOT include any markdown code blocks.Do NOT wrap the JSON in json, , or any backticks.Do NOT add explanations, notes, extra text, or comments."
            )
        )
        try:
            logger.debug(f"Generating plan for message: {message}")
            result = self._call_with_retry(
                lambda: self.planner.invoke([system, HumanMessage(content=message)])
            )
            logger.debug(f"Plan generation result: {result}")
            
            if result is None:
                logger.warn("Plan generation returned None")
                return PlanOutput(plan=[], todos=[], summary="")
            if isinstance(result, dict):
                result = PlanOutput(**cast(dict[str, Any], result))
            
            if isinstance(result, PlanOutput):
                # Fallback: if todos are empty but plan exists, generate todos from plan
                if result.plan and not result.todos:
                    logger.info("Todos missing from LLM output, generating from plan")
                    result.todos = [
                        TodoItem(id=str(uuid.uuid4()), title=step, status="pending") 
                        for step in result.plan
                    ]
                return result

            logger.warn(f"Plan generation returned unexpected type: {type(result)}")
            return PlanOutput(plan=[], todos=[], summary="")
        except Exception as e:
            logger.error(f"Plan generation failed: {e}", exc_info=True)
            return PlanOutput(plan=[], todos=[], summary="")

    async def invoke_stream(
        self, thread_id: str, user_id: str, message: str, background_tasks: Any = None
    ):
        # 1. Generate Plan
        yield {"type": "status", "content": "Analyzing request..."}
        plan = self.plan(message)
        
        # NOTE: We need to pass the plan/todos to the agent executor so it knows what to do!
        # The agent uses the system prompt and conversation history.
        # We must inject the generated plan into the conversation context or system prompt for this run.
        
        plan_context = ""
        if plan:
            yield {"type": "plan", "plan": plan.plan, "summary": plan.summary}
            if plan.todos:
                self.todo_store.write(thread_id, plan.todos)
                yield {"type": "todos", "todos": [t.model_dump() for t in plan.todos]}
                
                # Format plan for the agent
                plan_text = "\n".join([f"- {t.title} (ID: {t.id})" for t in plan.todos])
                plan_context = f"\n\nCURRENT PLAN:\n{plan_text}\n\nExecute the plan step-by-step using available tools. Update the todo status as you proceed. IF A TOOL IS AVAILABLE TO SOLVE THE TASK, YOU MUST USE IT. IMPORTANT: After each step, you MUST use the 'write_todos' tool to mark the corresponding task as 'completed'."
        
        # 2. Prepare Context
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": user_id},
            "recursion_limit": self.settings.recursion_limit
        }
        
        # Load history and facts
        items = store_all(user_id)
        relevant = store_search(self.store, user_id, query=message, limit=8)
        facts = [str(m.value) for m in relevant]
        
        messages = []
        # Inject plan context into the system message for THIS turn
        system_content = self._system_prompt()
        if facts:
            system_content += "\n\nRelevant memory:\n" + "\n".join(facts)
        
        if plan_context:
            system_content += plan_context
            
        # We can't easily replace the system prompt of the compiled graph dynamically without rebuilding it
        # OR we can pass it as a SystemMessage at the start of the conversation window for this turn.
        # LangGraph usually appends messages.
        
        messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": message})
        
        yield {"type": "status", "content": "Thinking..."}

        # 3. Stream Execution
        # AsyncSqliteSaver.from_conn_string returns an async context manager
        async with create_checkpointer(thread_id) as checkpointer:
             # Create agent with the specific system prompt for this turn (including plan)
             # Note: create_deep_agent takes 'system_prompt'. 
             # If we want dynamic system prompts per turn in LangGraph, passing it as a message is often better 
             # than rebuilding the graph, BUT create_deep_agent likely fixes the system prompt node.
             # Let's rebuild it to be safe and simple.
             
            agent_executor = create_deep_agent(
                model=self.chat_model,
                tools=self.toolbox.tools(),
                checkpointer=checkpointer,
                store=self.store,
                system_prompt=system_content, # Pass the dynamic prompt here
                backend=FilesystemBackend(root_dir=str(resolve_path(self.settings.workspace_root))),
            )

            try:
                async for event in agent_executor.astream_events(
                    {"messages": messages}, 
                    config=config, 
                    version="v1"
                ):
                    kind = event["event"]
                    
                    if kind == "on_chat_model_stream":
                        content = event["data"]["chunk"].content
                        if content:
                            yield {"type": "token", "content": content}
                    
                    elif kind == "on_tool_start":
                        tool_name = event["name"]
                        tool_input = event["data"].get("input")
                        
                        # Log detailed tool start
                        logger.info(f"Agent starting tool: {tool_name} with input: {str(tool_input)[:500]}")
                        
                        yield {"type": "tool_start", "tool": tool_name, "input": tool_input}
                        yield {"type": "status", "content": f"Running {tool_name}..."}
                        
                        # Update todo status to 'in_progress' if we can match the tool to a step
                        # For simplicity, if we have a pending todo that matches the tool intent (or just the first pending one)
                        # we mark it in_progress.
                        
                        # Auto-update logic: Find the first 'pending' todo and mark it 'in_progress'
                        if tool_name != "write_todos":
                            current_todos = self.todo_store.get(thread_id)
                            first_pending = next((t for t in current_todos if t.status == "pending"), None)
                            if first_pending:
                                first_pending.status = "in_progress"
                                self.todo_store.write(thread_id, current_todos)
                                yield {"type": "todos", "todos": [t.model_dump() for t in current_todos]}
                        
                        if tool_name == "write_todos":
                            # If the agent explicitly updates todos, we stream the update
                            # write_todos input is {"todos": [...], "merge": bool}
                            pass 
                            
                    elif kind == "on_tool_end":
                        tool_output = event["data"].get("output")
                        
                        # Log detailed tool end
                        logger.info(f"Agent finished tool: {event['name']} with output: {str(tool_output)[:500]}")
                        
                        yield {"type": "tool_end", "tool": event["name"], "output": str(tool_output)}
                        yield {"type": "status", "content": f"Finished {event['name']}"}
                        
                        # If tool was write_todos, refresh the client's todo list
                        if event["name"] == "write_todos":
                             # We need to fetch the updated state from the store
                             current_todos = self.todo_store.get(thread_id)
                             yield {"type": "todos", "todos": [t.model_dump() for t in current_todos]}
                        else:
                             # Auto-update logic: If a tool finished successfully, we *could* mark it complete,
                             # BUT that assumes one tool = one task. 
                             # Safer to just mark it in_progress at start, and let the agent mark complete explicitly.
                             # Or we can mark the currently in_progress task as completed?
                             # Let's rely on the agent for completion, but force update if it forgets.
                             pass
            except Exception as e:
                logger.error(f"Stream execution failed: {e}", exc_info=True)
                yield {"type": "status", "content": f"Error: {str(e)}"}
                # Don't re-raise if we want to keep the connection alive (but ASGI might close it)
                # yield [DONE] will be sent by main.py

            # 4. Finalize & Auto-complete in_progress tasks
            # If the loop finishes naturally (no error), it means the agent is done.
            # We should check if there's any task left 'in_progress' and mark it completed.
            try:
                final_todos = self.todo_store.get(thread_id)
                updated = False
                for t in final_todos:
                    if t.status == "in_progress":
                        t.status = "completed"
                        updated = True
                
                if updated:
                    self.todo_store.write(thread_id, final_todos)
                    yield {"type": "todos", "todos": [t.model_dump() for t in final_todos]}
                    logger.info("Auto-completed remaining in_progress tasks.")
            except Exception as e:
                logger.warn(f"Failed to auto-complete todos: {e}")


        # 4. Finalize (Store memory, etc.)
        # Ideally we'd capture the final state here. 
        # Since astream_events yields granular events, we might need to 
        # reconstruct the final reply or rely on the client to assemble tokens.
        
        # For memory storage, we might need to invoke a separate non-streaming save
        # or capture the full reply from the aggregated tokens.
        
        # For this PoC, we assume the client handles the aggregation.
        # But we DO need to save the turn. 
        # We can't easily get the *full* final reply from astream_events without accumulating.
        # So let's accumulate tokens.
        
        # (Accumulation logic would go inside the loop above)
        
        # Trigger background summary if needed
        # if background_tasks: ...

