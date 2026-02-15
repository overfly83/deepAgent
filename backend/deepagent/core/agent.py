from __future__ import annotations

import asyncio
import json
import os
import random
import time
import uuid
from datetime import datetime
from threading import get_ident
from typing import Any, cast

import httpx
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from deepagent.common.config import get_settings, resolve_path
from deepagent.common.logger import get_logger
from deepagent.common.schemas import TodoItem
from deepagent.core.prompts import AGENT_SYSTEM_PROMPT
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
from deepagent.core.planner import Planner
from deepagent.core.execution import ExecutionEngine
from deepagent.core.observer import PlanObserver
from deepagent.integrations.mcp_client import MCPRegistry
from deepagent.integrations.skills import SkillRegistry

from deepagent.common.exceptions import (
    AgentErrorHandler,
    PlanGenerationError,
    AgentStreamError
)

logger = get_logger("deepagent.core.agent")

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

        self.toolbox = ToolBox(
            todo_store=self.todo_store,
            memory_store=self.store,
            mcp_registry=self.mcp_registry,
            skill_registry=self.skill_registry,
            subagent_fn=self._run_subagent,
        )
        
        self.planner = Planner(self.model_router, self.toolbox)
        self.execution_engine = ExecutionEngine(self.todo_store, self.toolbox)
        self.observer = PlanObserver(self.model_router)

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

        return AGENT_SYSTEM_PROMPT.format(tools_description=mcp_tools_desc)

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

    def plan(self, message: str):
        """Generate a plan based on the user's message."""
        try:
            logger.debug(f"Generating plan for message: {message}")
            result = self.planner.generate_plan(message)
            logger.debug(f"Plan generation result: {result}")
            
            # Fallback: if todos are empty but plan exists, generate todos from plan
            if result.plan and not result.todos:
                logger.info("Todos missing from LLM output, generating from plan")
                result.todos = [
                    TodoItem(id=str(uuid.uuid4()), title=step, status="pending") 
                    for step in result.plan
                ]
            return result
        except Exception as e:
            # Wrap generic exception
            error_event = AgentErrorHandler.format_error(PlanGenerationError("Failed to generate plan", original_error=e))
            # We can't yield here easily as this is a sync method returning PlanOutput
            # But we can log it properly
            logger.error(f"Plan generation failed: {e}", exc_info=True)
            return type('PlanOutput', (), {'plan': [], 'todos': [], 'summary': ''})()

    def invoke(self, thread_id: str, user_id: str, message: str, background_tasks: Any = None):
        """Non-streaming version of invoke_stream that returns the full result."""
        import asyncio
        
        async def collect_events():
            events = []
            async for event in self.invoke_stream(thread_id, user_id, message, background_tasks):
                events.append(event)
            return events
        
        events = asyncio.run(collect_events())
        
        # Process events to extract the final result
        reply = ""
        plan = []
        summary = ""
        todos = []
        
        for event in events:
            if event.get("type") == "token":
                reply += event.get("content", "")
            elif event.get("type") == "plan":
                plan = event.get("plan", [])
                summary = event.get("summary", "")
            elif event.get("type") == "todos":
                todos = event.get("todos", [])
        
        # Get relevant memories
        relevant = store_search(self.store, user_id, query=message, limit=8)
        memories = [str(m.value) for m in relevant]
        
        return {
            "reply": reply,
            "plan": plan,
            "summary": summary,
            "todos": todos,
            "memories": memories
        }

    async def invoke_stream(
        self, thread_id: str, user_id: str, message: str, background_tasks: Any = None
    ):
        try:
            # 1. Generate Plan
            yield {"type": "status", "content": "Analyzing request..."}
            try:
                plan = self.plan(message)
                logger.info(f"Generated Plan:\n{plan.plan}\nTodos:\n{[t.title for t in plan.todos]}")
            except Exception as e:
                 raise PlanGenerationError("Plan generation step failed", original_error=e)
            
            # 2. Analyze Plan with Observer
            if plan:
                yield {"type": "status", "content": "Analyzing plan..."}
                observer_feedback = self.observer.update(
                    type="plan",
                    plan=plan.plan,
                    todos=plan.todos
                )
                
                if observer_feedback:
                    yield {"type": "observer_feedback", "feedback": observer_feedback["feedback"]}
                    logger.info(f"Observer feedback on plan: {observer_feedback['feedback'][:100]}...")
            
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
                    
                    # Add observer feedback to plan context if available
                    if observer_feedback:
                        plan_context += f"\n\nOBSERVER FEEDBACK:\n{observer_feedback['feedback']}"
            
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

                accumulated_reply = ""
                current_task = None
                try:
                    async for event in self.execution_engine.execute_plan(
                        thread_id, agent_executor, messages, config
                    ):
                        if event.get("type") == "token":
                            accumulated_reply += event.get("content", "")
                        
                        # Track current task
                        if event.get("type") == "tool_start" and event.get("tool") != "write_todos":
                            # Get the current task being executed
                            current_todos = self.todo_store.get(thread_id)
                            current_task = next((t for t in current_todos if t.status == "in_progress"), None)
                        
                        # Handle task completion and analyze result with observer
                        elif event.get("type") == "tool_end" and event.get("tool") != "write_todos":
                            if current_task:
                                tool_output = event.get("output", "")
                                
                                # Get remaining tasks
                                current_todos = self.todo_store.get(thread_id)
                                remaining_tasks = [t for t in current_todos if t.status != "completed"]
                                
                                # Analyze task result with observer
                                observer_feedback = self.observer.update(
                                    type="task_result",
                                    task=current_task,
                                    result=tool_output,
                                    remaining_tasks=remaining_tasks
                                )
                                
                                if observer_feedback:
                                    yield {"type": "observer_feedback", "feedback": observer_feedback["feedback"]}
                                    logger.info(f"Observer feedback on task '{current_task.title}': {observer_feedback['feedback'][:100]}...")
                                    
                                    # Update plan context with observer feedback for next steps
                                    if plan_context:
                                        plan_context += f"\n\nOBSERVER FEEDBACK ON '{current_task.title}':\n{observer_feedback['feedback']}"
                        
                        yield event
                except Exception as e:
                    # Capture stream errors
                    raise AgentStreamError("Error during agent execution stream", original_error=e)
                
                # Log the final reply
                if accumulated_reply:
                    logger.info(f"Final Agent Reply:\n{accumulated_reply}")

        except Exception as e:
            # Global error handler for the stream
            # If a critical error occurs, mark all pending/in_progress tasks as failed
            try:
                current_todos = self.todo_store.get(thread_id)
                updated = False
                for t in current_todos:
                    if t.status in ["pending", "in_progress"]:
                        t.status = "failed"
                        updated = True
                
                if updated:
                    self.todo_store.write(thread_id, current_todos)
                    yield {"type": "todos", "todos": [t.model_dump() for t in current_todos]}
                    logger.warn("Marked all pending tasks as failed due to critical exception.")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup todos during error handling: {cleanup_error}")

            error_response = AgentErrorHandler.format_error(e)
            yield error_response


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