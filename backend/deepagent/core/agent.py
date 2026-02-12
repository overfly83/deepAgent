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

    @field_validator("plan", pre=True)
    def parse_plan(cls, v):
        if isinstance(v, str):
            return [v]
        return v
        
    @field_validator("todos", pre=True)
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
        return """
            You are DeepAgent, a structured, context-aware assistant designed to handle tasks efficiently through systematic planning, context management, specialized subagent collaboration, and persistent long-term memory. Adhere strictly to the following guidelines, integrating all core capabilities into your workflow:
            1. Core Identity & Fundamental Requirements: Always act as DeepAgent. For every task—whether simple or complex—first decompose it into a clear, concise short plan (1-5 discrete, actionable steps), and consistently maintain and update your task list using the built-in write_todos tool. Prioritize recalling user history across all sessions, extract durable, relevant facts from interactions, and store them permanently using the memory_put tool to ensure continuity and avoid redundant work.

            2. Planning and Task Decomposition (via write_todos): Leverage the built-in write_todos tool as the foundation of your workflow. Break down complex tasks into small, manageable, discrete steps that can be executed sequentially or in parallel (as needed). Track progress on each todo item in real time—mark steps as completed once finished, update steps if new information emerges or requirements change, and remove irrelevant steps to keep the task list focused. Ensure each todo is specific (e.g., "Read the config file to extract API keys" instead of "Handle config") and aligned with the overall task goal.

            3. Context Management (via File System Tools): Utilize the provided file system tools (ls, read_file, write_file, edit_file) proactively to manage context efficiently. Offload large chunks of context (e.g., long documents, detailed logs, complex data structures) to in-memory or filesystem storage instead of keeping them in the prompt window—this prevents context overflow and ensures you can work seamlessly with variable-length tool results. When working with files: use ls to explore the file structure first, read_file to access content only when needed, write_file to save intermediate results or persistent data, and edit_file to modify existing content incrementally. Always reference stored file paths in your todos and plans for easy retrieval.

            4. Subagent Spawning (via Task Tool): Use the built-in task tool to spawn specialized subagents when appropriate, focusing on context isolation. Deploy subagents for narrow, deep subtasks (e.g., "Validate type annotations with mypy", "Summarize the user’s previous session history") that would clutter the main agent’s context or require specialized expertise. Keep the main agent’s context clean by delegating these subtasks to subagents, and ensure subagents return clear, actionable results that the main agent can integrate into its overall plan. Track subagent progress via write_todos and retrieve their outputs promptly to maintain workflow continuity.

            5. Long-Term Memory (via LangGraph’s Memory Store): Extend your capabilities with persistent memory across all threads using LangGraph’s Memory Store. Use memory_put to save durable facts (e.g., user preferences, key project details, previously confirmed conclusions, API credentials) from each conversation—avoid storing temporary or irrelevant information (e.g., intermediate todo updates, failed tool outputs). Before starting a new task or responding to a user query, recall relevant user history and stored facts to ensure consistency across sessions. If a fact is unclear or missing, use your tools to verify or request clarification, then update the memory store accordingly.

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
        system = SystemMessage(
            content=(
                "You are a planning assistant. Analyze the user's request and produce a structured plan.\n"
                "Return a JSON object with:\n"
                "- 'plan': A list of high-level steps (strings). If only one step, return a list with one string.\n"
                "- 'todos': A list of actionable items, each with a 'title' and a unique 'id' (string).\n"
                "- 'summary': A brief summary of the intent.\n"
            )
        )
        try:
            logger.debug(f"Generating plan for message: {message}")
            result = self.planner.invoke([system, HumanMessage(content=message)])
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

    def invoke(self, thread_id: str, user_id: str, message: str, background_tasks: Any = None) -> dict[str, Any]:
        plan = self.plan(message)
        if plan and plan.todos:
            self.todo_store.write(thread_id, plan.todos)
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": user_id},
            "recursion_limit": self.settings.recursion_limit
        }
        items = store_all(user_id)
        history: list[dict[str, str]] = []
        user_messages: list[str] = []
        conversations: list[dict[str, Any]] = []
        latest_summary = ""
        for item in items:
            value = item.get("value") if isinstance(item, dict) else None
            if isinstance(value, dict) and value.get("type") == "conversation":
                conversations.append(value)
                um = value.get("user_message")
                ar = value.get("agent_reply")
                if isinstance(um, str) and um:
                    user_messages.append(um)
                if isinstance(um, str) and um:
                    history.append({"role": "user", "content": um})
                if isinstance(ar, str) and ar:
                    history.append({"role": "assistant", "content": ar})
            if isinstance(value, dict) and value.get("type") == "summary":
                latest_summary = value.get("summary") or latest_summary
        first_question = user_messages[0] if user_messages else ""
        normalized = message.lower()
        if first_question and (
            "first question" in normalized
            or "first thing i asked" in normalized
            or "what did i ask first" in normalized
        ):
            reply = f"Your first question was: {first_question}"
            try:
                store_put(
                    self.store,
                    user_id,
                    {
                        "type": "conversation",
                        "thread_id": thread_id,
                        "user_message": message,
                        "agent_reply": reply,
                        "summary": plan.summary if plan else "",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                )
            except Exception:
                pass
            todos = self.todo_store.get(thread_id)
            memories = [m.dict() for m in store_search(self.store, user_id, query=message)]
            return {
                "reply": reply,
                "plan": plan.plan if plan else [],
                "todos": [t.model_dump() for t in todos],
                "memories": memories,
            }
        if self.settings.use_compressed_history:
            history = history[-5:]
        else:
            history = history[-20:]
        relevant = store_search(self.store, user_id, query=message, limit=8)
        facts: list[str] = []
        for m in relevant:
            try:
                facts.append(str(m.value))
            except Exception:
                facts.append(str(m))
        if latest_summary:
            facts.append(f"Conversation summary:\n{latest_summary}")
        keywords = [w for w in re.findall(r"[a-zA-Z0-9]+", normalized) if len(w) > 3]
        if keywords:
            scored: list[tuple[int, dict[str, Any]]] = []
            for item in items:
                value = item.get("value") if isinstance(item, dict) else None
                if not isinstance(value, dict):
                    continue
                text = f"{value.get('user_message','')} {value.get('agent_reply','')}".lower()
                score = sum(1 for w in keywords if w in text)
                if score:
                    scored.append((score, value))
            scored.sort(key=lambda x: x[0], reverse=True)
            for _, value in scored[:5]:
                facts.append(str(value))
        messages: list[dict[str, str]] = []
        
        # Build the system prompt content
        system_content_parts = []
        
        # Add Relevant Memory section
        if facts:
            system_content_parts.append("Relevant memory:\n" + "\n".join(facts))
            
        # Add Recent History section
        if history:
            history_text_parts = ["Recent conversation history:"]
            for msg in history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                history_text_parts.append(f"{role}: {content}")
            system_content_parts.append("\n".join(history_text_parts))
            
        # Add default system prompt if needed (though the agent likely has its own base prompt, 
        # injecting context here ensures it's available)
        
        if system_content_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_content_parts)})
            
        messages.append({"role": "user", "content": message})
        
        logger.debug(f"LLM Input Messages: {json.dumps([m for m in messages], default=str)}")
        
        result = self._call_with_retry(
            lambda: self._get_agent(thread_id).invoke(
                {"messages": messages},
                config=config,
            )
        )
        
        if result and result.get("messages"):
             logger.debug(f"LLM Output: {result['messages'][-1].content}")

        if result is None:
            return {
                "reply": "Rate limit reached. Please retry in a moment.",
                "plan": plan.plan if plan else [],
                "todos": [t.model_dump() for t in self.todo_store.get(thread_id)],
                "memories": [m.dict() for m in store_search(self.store, user_id, query=message)],
            }
        reply = result["messages"][-1].content if result.get("messages") else ""
        try:
            store_put(
                self.store,
                user_id,
                {
                    "type": "conversation",
                    "thread_id": thread_id,
                    "user_message": message,
                    "agent_reply": str(reply),
                    "summary": plan.summary if plan else "",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            )
        except Exception:
            pass
        try:
            updated_items = store_all(user_id)
            updated_conversations: list[dict[str, Any]] = []
            for item in updated_items:
                value = item.get("value") if isinstance(item, dict) else None
                if isinstance(value, dict) and value.get("type") == "conversation":
                    updated_conversations.append(value)
            if background_tasks:
                background_tasks.add_task(self._maybe_store_summary, user_id, thread_id, updated_items, updated_conversations)
            else:
                self._maybe_store_summary(user_id, thread_id, updated_items, updated_conversations)
        except Exception:
            pass
        todos = self.todo_store.get(thread_id)
        memories = [m.dict() for m in store_search(self.store, user_id, query=message)]
        return {
            "reply": str(reply),
            "plan": plan.plan if plan else [],
            "todos": [t.model_dump() for t in todos],
            "memories": memories,
        }
