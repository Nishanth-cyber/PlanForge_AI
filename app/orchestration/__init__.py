"""PlanForge Orchestration Subsystem.

Coordinates the 10-stage generative residential floor-plan pipeline:
Requirement -> Planning -> ASAA -> Architectural LLM -> Geometry ->
Validation -> Refinement -> Multi-Design Diversity -> Decision Trace -> Export.
"""

from app.orchestration.config import OrchestrationConfig
from app.orchestration.errors import (
    IncompleteRequirementsError,
    OrchestrationError,
    PipelineConfigurationError,
    StageExecutionError,
)
from app.orchestration.orchestrator import (
    PlanForgeOrchestrator,
    create_default_orchestrator,
)
from app.orchestration.pipeline import PipelineResult
from app.orchestration.state import PipelineState, StageName, StageRecord, StageStatus

__all__ = [
    "OrchestrationConfig",
    "OrchestrationError",
    "StageExecutionError",
    "IncompleteRequirementsError",
    "PipelineConfigurationError",
    "PlanForgeOrchestrator",
    "create_default_orchestrator",
    "PipelineResult",
    "PipelineState",
    "StageName",
    "StageStatus",
    "StageRecord",
]
