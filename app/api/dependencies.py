"""FastAPI dependency providers for the PlanForge REST API."""

from __future__ import annotations

from typing import Optional

from app.api.registry import ProjectRegistry, get_default_registry
from app.orchestration.orchestrator import (
    PlanForgeOrchestrator,
    create_default_orchestrator,
)

# Shared orchestrator instance
_DEFAULT_ORCHESTRATOR: Optional[PlanForgeOrchestrator] = None


def get_orchestrator() -> PlanForgeOrchestrator:
    """Dependency provider returning the active PlanForgeOrchestrator instance."""
    global _DEFAULT_ORCHESTRATOR
    if _DEFAULT_ORCHESTRATOR is None:
        _DEFAULT_ORCHESTRATOR = create_default_orchestrator()
    return _DEFAULT_ORCHESTRATOR


def get_project_registry() -> ProjectRegistry:
    """Dependency provider returning the active ProjectRegistry instance."""
    return get_default_registry()
