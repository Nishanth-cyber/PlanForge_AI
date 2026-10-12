"""Design Editing Agent package for PlanForge AI."""

from app.agents.editing_agent.agent import DesignEditingAgent, EditResult
from app.agents.editing_agent.intent import EditIntentResult, EditIntentType, detect_edit_intent
from app.agents.editing_agent.operations import EditOperation, EditOperationType, EditPlan
from app.agents.editing_agent.versioning import DesignVersion, ProjectVersionHistory

__all__ = [
    "DesignEditingAgent",
    "EditResult",
    "EditIntentType",
    "EditIntentResult",
    "detect_edit_intent",
    "EditOperationType",
    "EditOperation",
    "EditPlan",
    "DesignVersion",
    "ProjectVersionHistory",
]
