import re
from typing import AsyncGenerator, Dict, Any, List

from deepagent.core.memory import create_checkpointer
from deepagent.core.todos import TodoStore
from deepagent.core.toolbox import ToolBox
from deepagent.common.schemas import TodoItem

class ExecutionEngine:
    def __init__(self, todo_store: TodoStore, toolbox: ToolBox):
        self.todo_store = todo_store
        self.toolbox = toolbox
    
    async def execute_plan(
        self, 
        thread_id: str, 
        agent_executor, 
        messages: List[Dict[str, Any]], 
        config: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute the plan using LangGraph and yield events."""
        accumulated_reply = ""
        
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
                    accumulated_reply += content
            
            elif kind == "on_tool_start":
                tool_name = event["name"]
                tool_input = event["data"].get("input")
                
                yield {"type": "tool_start", "tool": tool_name, "input": tool_input}
                yield {"type": "status", "content": f"Running {tool_name}..."}
                
                # Auto-update logic: Find the first 'pending' todo and mark it 'in_progress'
                if tool_name != "write_todos":
                    current_todos = self.todo_store.get(thread_id)
                    first_pending = next((t for t in current_todos if t.status == "pending"), None)
                    if first_pending:
                        first_pending.status = "in_progress"
                        self.todo_store.write(thread_id, current_todos)
                        yield {"type": "todos", "todos": [t.model_dump() for t in current_todos]}
            
            elif kind == "on_tool_end":
                tool_output = event["data"].get("output")
                tool_name = event["name"]
                
                yield {"type": "tool_end", "tool": tool_name, "output": str(tool_output)}
                yield {"type": "status", "content": f"Finished {tool_name}"}
                
                # Check for failure in tool output
                is_failed = self._is_tool_failed(tool_output)
                
                # If tool was write_todos, refresh the client's todo list
                if tool_name == "write_todos":
                     current_todos = self.todo_store.get(thread_id)
                     yield {"type": "todos", "todos": [t.model_dump() for t in current_todos]}
                else:
                     # Auto-update logic
                     current_todos = self.todo_store.get(thread_id)
                     in_progress_task = next((t for t in current_todos if t.status == "in_progress"), None)
                     
                     if in_progress_task:
                         if is_failed:
                             in_progress_task.status = "failed"
                         else:
                             # If success, auto-complete it
                             in_progress_task.status = "completed"
                          
                         self.todo_store.write(thread_id, current_todos)
                         yield {"type": "todos", "todos": [t.model_dump() for t in current_todos]}
        
        # Finalize & Auto-complete in_progress tasks
        final_todos = self.todo_store.get(thread_id)
        updated = False
        for t in final_todos:
            if t.status == "in_progress":
                t.status = "completed"
                updated = True
        
        if updated:
            self.todo_store.write(thread_id, final_todos)
            yield {"type": "todos", "todos": [t.model_dump() for t in final_todos]}
    
    def _is_tool_failed(self, tool_output: Any) -> bool:
        """Check if a tool execution failed."""
        is_failed = False
        output_str = str(tool_output)
        
        try:
            if '"success": false' in output_str:
                is_failed = True
            elif "Rate limited" in output_str:
                is_failed = True
            # Check for "isError": true (with flexible spacing)
            elif re.search(r'"isError"\s*:\s*true', output_str):
                is_failed = True
            # Only flag "Error" if it's not part of "isError": false
            elif "Error" in output_str and '"isError": false' not in output_str and '"isError":false' not in output_str:
                if "Traceback" in output_str or "Exception" in output_str:
                    is_failed = True
        except Exception:
            if '"success": false' in output_str or "Rate limited" in output_str:
                is_failed = True
        
        return is_failed