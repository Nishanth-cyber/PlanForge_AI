"""Structured response contract for the conversational PlanForge assistant.

The backend decides *what kind of response* a turn is (``ResponseType``), which
interactive options (if any) accompany it, and which validated ``ChatAction`` (if any)
the client may execute. The frontend only renders what it is told.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict


class ResponseType(str, Enum):
    """How the client must render an assistant turn."""

    TEXT = "text"                                  # plain conversational answer
    QUICK_REPLIES = "quick_replies"                # small optional set of relevant choices
    CLARIFICATION = "clarification"                # exactly one missing requirement to resolve
    REQUIREMENT_SUMMARY = "requirement_summary"    # structured summary of collected requirements
    GENERATION_PROGRESS = "generation_progress"    # real backend generation status
    GENERATION_RESULT = "generation_result"        # generated design + validation results
    ACTION_RESULT = "action_result"                # result of export / validation / inspection


class ConversationIntent(str, Enum):
    """Fine-grained intent of a user message (semantic, context-aware)."""

    GREETING = "GREETING"
    CAPABILITY_QUERY = "CAPABILITY_QUERY"
    PROJECT_TYPE_SELECTION = "PROJECT_TYPE_SELECTION"
    REQUIREMENT_INPUT = "REQUIREMENT_INPUT"
    REQUIREMENT_CLARIFICATION = "REQUIREMENT_CLARIFICATION"
    REQUIREMENT_CORRECTION = "REQUIREMENT_CORRECTION"
    PROJECT_SUMMARY = "PROJECT_SUMMARY"
    GENERATE_FLOOR_PLAN = "GENERATE_FLOOR_PLAN"
    DESIGN_MODIFICATION = "DESIGN_MODIFICATION"
    VALIDATION_QUERY = "VALIDATION_QUERY"
    EXPORT_REQUEST = "EXPORT_REQUEST"
    PROJECT_STATUS = "PROJECT_STATUS"
    GENERAL_ARCHITECTURAL_QUERY = "GENERAL_ARCHITECTURAL_QUERY"
    AMBIGUOUS_REQUEST = "AMBIGUOUS_REQUEST"


#: Intents that collect or modify structured requirements (handled by the Requirement Agent).
REQUIREMENT_INTENTS = frozenset(
    {
        ConversationIntent.PROJECT_TYPE_SELECTION,
        ConversationIntent.REQUIREMENT_INPUT,
        ConversationIntent.REQUIREMENT_CLARIFICATION,
        ConversationIntent.REQUIREMENT_CORRECTION,
    }
)


class ConversationStage(str, Enum):
    """Workflow stage of the conversation (backend-owned)."""

    DISCOVERY = "DISCOVERY"
    COLLECTING_REQUIREMENTS = "COLLECTING_REQUIREMENTS"
    READY_TO_GENERATE = "READY_TO_GENERATE"
    GENERATING = "GENERATING"
    REVIEWING_DESIGN = "REVIEWING_DESIGN"


#: The only action types the backend will ever emit / the client may execute.
ACTION_TYPES = frozenset({"generate_floor_plan", "export", "validation", "inspect"})


@dataclass(frozen=True)
class QuickReply:
    """One optional, relevant choice shown under an assistant message."""

    label: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"label": self.label, "value": self.value}


@dataclass
class ChatAction:
    """A validated operation the client may execute (or has been told the result of)."""

    type: str
    label: str = ""
    status: str = "ready"            # ready | unavailable | completed | failed
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    auto_execute: bool = False       # True only when the user explicitly asked for it
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in ACTION_TYPES:
            raise ValueError(f"Unsupported chat action type: {self.type!r}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
