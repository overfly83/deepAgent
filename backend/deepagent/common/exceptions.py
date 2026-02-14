from typing import Any, Dict, Optional
from deepagent.common.logger import get_logger

logger = get_logger("deepagent.common.exceptions")

class DeepAgentException(Exception):
    """Base exception for DeepAgent errors."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error

class PlanGenerationError(DeepAgentException):
    """Raised when plan generation fails."""
    pass

class ToolExecutionError(DeepAgentException):
    """Raised when a tool fails unexpectedly."""
    pass

class AgentStreamError(DeepAgentException):
    """Raised during the agent's execution stream."""
    pass

class AgentErrorHandler:
    """Centralized handler for agent exceptions."""
    
    @staticmethod
    def format_error(e: Exception) -> Dict[str, Any]:
        """Format an exception into a structured error response for the frontend."""
        error_type = type(e).__name__
        message = str(e)
        
        # Determine user-friendly message based on exception type
        user_message = "An unexpected error occurred."
        severity = "error"
        
        if isinstance(e, PlanGenerationError):
            user_message = f"Failed to generate a plan: {message}"
            severity = "warning"
        elif isinstance(e, ToolExecutionError):
            user_message = f"Tool execution failed: {message}"
            severity = "warning"
        elif isinstance(e, AgentStreamError):
            user_message = f"Agent execution interrupted: {message}"
            severity = "error"
        else:
            # Generic fallback
            user_message = f"System Error ({error_type}): {message}"
            
        logger.error(f"Agent Error: {user_message}", exc_info=e)
        
        return {
            "type": "error",
            "content": user_message,
            "error_type": error_type,
            "severity": severity
        }
