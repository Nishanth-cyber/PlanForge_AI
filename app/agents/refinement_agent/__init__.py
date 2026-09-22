"""Refinement Agent package for PlanForge AI.

Exports:
- RefinementAgent: LLM-driven architectural correction agent
- RefinementLoop: Orchestrator of the iterative validation-refinement cycle
- RefinementContext, RefinementContextBuilder: Immutable context packaging
- RefinementOutputValidator: Response schema and constraint validation
- RefinementStatus, RefinementChange, RefinementIterationRecord, RefinementResult: Data contracts
"""

from app.agents.refinement_agent.agent import RefinementAgent
from app.agents.refinement_agent.context import (
    RefinementContext,
    RefinementContextBuilder,
)
from app.agents.refinement_agent.loop import RefinementLoop
from app.agents.refinement_agent.output_validator import RefinementOutputValidator
from app.models.refinement import (
    RefinementChange,
    RefinementIterationRecord,
    RefinementResult,
    RefinementStatus,
)

__all__ = [
    "RefinementAgent",
    "RefinementLoop",
    "RefinementContext",
    "RefinementContextBuilder",
    "RefinementOutputValidator",
    "RefinementStatus",
    "RefinementChange",
    "RefinementIterationRecord",
    "RefinementResult",
]
