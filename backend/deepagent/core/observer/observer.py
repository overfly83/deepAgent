from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

from langchain_core.messages import HumanMessage, SystemMessage

from deepagent.common.schemas import TodoItem
from deepagent.core.observer.prompts import OBSERVER_PLAN_ANALYSIS_PROMPT, OBSERVER_TASK_ANALYSIS_PROMPT
from deepagent.core.models import ModelRouter

class Observer(ABC):
    """Abstract base class for observers."""
    
    @abstractmethod
    def update(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Update the observer with new information."""
        pass

class PlanObserver(Observer):
    """Observer that monitors plans and task results, providing suggestions."""
    
    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router
        self.chat_model = self.model_router.get_model("chat")
    
    def update(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Update the observer with new information."""
        update_type = kwargs.get("type")
        
        if update_type == "plan":
            return self._analyze_plan(kwargs.get("plan"), kwargs.get("todos"))
        elif update_type == "task_result":
            return self._analyze_task_result(
                kwargs.get("task"), 
                kwargs.get("result"), 
                kwargs.get("remaining_tasks")
            )
        return None
    
    def _analyze_plan(self, plan: List[str], todos: List[TodoItem]) -> Dict[str, Any]:
        """Analyze the plan and provide suggestions for improvement."""
        system = SystemMessage(content=OBSERVER_PLAN_ANALYSIS_PROMPT)
        
        plan_text = "\n".join([f"- {step}" for step in plan])
        todos_text = "\n".join([f"- {todo.title} (status: {todo.status})" for todo in todos])
        
        message = HumanMessage(
            content=f"Plan:\n{plan_text}\n\nTodos:\n{todos_text}\n\nPlease analyze this plan and provide suggestions for improvement."
        )
        
        response = self.chat_model.invoke([system, message])
        
        return {
            "type": "plan_feedback",
            "feedback": response.content,
            "plan": plan,
            "todos": todos
        }
    
    def _analyze_task_result(self, task: TodoItem, result: str, remaining_tasks: List[TodoItem]) -> Dict[str, Any]:
        """Analyze a task result and provide suggestions for adjusting the plan."""
        system = SystemMessage(content=OBSERVER_TASK_ANALYSIS_PROMPT)
        
        remaining_text = "\n".join([f"- {todo.title} (status: {todo.status})" for todo in remaining_tasks])
        
        message = HumanMessage(
            content=f"Completed Task:\n{task.title}\n\nTask Result:\n{result}\n\nRemaining Tasks:\n{remaining_text}\n\nPlease analyze this task result and provide suggestions for adjusting the plan."
        )
        
        response = self.chat_model.invoke([system, message])
        
        return {
            "type": "task_feedback",
            "task": task,
            "result": result,
            "feedback": response.content,
            "remaining_tasks": remaining_tasks
        }