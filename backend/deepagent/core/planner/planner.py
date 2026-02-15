from typing import List, Optional
import re
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from deepagent.common.schemas import TodoItem
from deepagent.core.planner.prompts import PLANNER_SYSTEM_PROMPT
from deepagent.core.models import ModelRouter
from deepagent.core.toolbox import ToolBox


def clean_json_response(response: str) -> str:
    """
    Clean up JSON response by removing code blocks, extra text, and ensuring valid JSON format.
    
    Args:
        response: The raw response from the LLM
        
    Returns:
        Cleaned JSON string
    """
    # Remove markdown code blocks
    json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
    if json_match:
        response = json_match.group(1)
    
    # Remove any backticks around JSON
    response = response.strip().strip('`')
    
    # Remove any text before or after the JSON object
    # Look for the first '{' and last '}'
    start_idx = response.find('{')
    end_idx = response.rfind('}')
    if start_idx != -1 and end_idx != -1:
        response = response[start_idx:end_idx+1]
    
    return response

class PlanOutput:
    def __init__(self, plan: List[str], todos: List[TodoItem], summary: str):
        self.plan = plan
        self.todos = todos
        self.summary = summary

class Planner:
    def __init__(self, model_router: ModelRouter, toolbox: ToolBox):
        self.model_router = model_router
        self.toolbox = toolbox
        self.planner_model = self.model_router.get_model("plan")
        
    def generate_plan(self, message: str) -> PlanOutput:
        """Generate a plan based on the user's message."""
        import json
        
        mcp_tools_desc = self._get_mcp_tools_description()
        
        system = SystemMessage(
            content=PLANNER_SYSTEM_PROMPT.format(tools_description=mcp_tools_desc)
        )
        
        # Use raw text output instead of structured output to have more control over parsing
        result = self.planner_model.invoke([system, HumanMessage(content=message)])
        
        # Clean the response to remove code blocks and ensure valid JSON
        cleaned_response = clean_json_response(result.content)
        
        try:
            # Parse the cleaned JSON
            parsed_data = json.loads(cleaned_response)
            
            # Extract plan, todos, and summary
            plan = parsed_data.get("plan", [])
            todos_data = parsed_data.get("todos", [])
            summary = parsed_data.get("summary", "")
            
            # Convert todos data to TodoItem objects
            from deepagent.common.schemas import TodoItem
            todos = []
            for todo_data in todos_data:
                # Ensure each todo has required fields
                todo_id = todo_data.get("id", str(uuid.uuid4()))
                title = todo_data.get("title", "")
                status = todo_data.get("status", "pending")
                todos.append(TodoItem(id=todo_id, title=title, status=status))
            
            return PlanOutput(
                plan=plan,
                todos=todos,
                summary=summary
            )
        except json.JSONDecodeError as e:
            # If parsing fails, log the error and return an empty plan
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to parse plan JSON: {e}")
            logger.error(f"Raw response: {result.content}")
            logger.error(f"Cleaned response: {cleaned_response}")
            return PlanOutput(
                plan=[],
                todos=[],
                summary=""
            )
    
    def _get_mcp_tools_description(self) -> str:
        """Get a description of available MCP tools."""
        mcp_tools_desc = ""
        try:
            self.toolbox._ensure_mcp_initialized()
            all_mcp_tools = []
            for server_name in self.toolbox.mcp_registry.servers:
                tools = self.toolbox.mcp_registry.list_tools(server_name)
                for t in tools:
                     all_mcp_tools.append(f"- {t['name']} (Server: {server_name}): {t['description']}")
            if all_mcp_tools:
                mcp_tools_desc = "\nAvailable Tools for Execution:\n" + "\n".join(all_mcp_tools)
        except Exception:
            pass
        return mcp_tools_desc