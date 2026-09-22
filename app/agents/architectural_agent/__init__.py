"""Architectural Agent package for PlanForge AI."""

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.architectural_agent.context import (
    ArchitecturalContext,
    ContextBuilder,
    FloorDesignContext,
    RoomDesignContext,
)
from app.agents.architectural_agent.prompts import (
    ARCHITECTURAL_SYSTEM_PROMPT,
    build_floor_prompt,
)
from app.agents.architectural_agent.structured_output import (
    AllocationMismatchError,
    ArchitecturalLLMError,
    ArchitecturalOutputValidator,
    DimensionExceedsAllocationError,
    InvalidShapeError,
    MalformedLLMResponseError,
    RoomCoverageError,
)

__all__ = [
    "ArchitecturalAgent",
    "ArchitecturalContext",
    "ContextBuilder",
    "FloorDesignContext",
    "RoomDesignContext",
    "ARCHITECTURAL_SYSTEM_PROMPT",
    "build_floor_prompt",
    "ArchitecturalOutputValidator",
    "ArchitecturalLLMError",
    "MalformedLLMResponseError",
    "RoomCoverageError",
    "AllocationMismatchError",
    "DimensionExceedsAllocationError",
    "InvalidShapeError",
]
