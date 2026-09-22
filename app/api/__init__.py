"""PlanForge API package exposing REST endpoints for floor-plan generation."""

from app.api.app import app, create_app
from app.api.registry import ProjectRegistry, get_default_registry
from app.api.schemas import (
    AlternativeSummarySchema,
    ExportResponse,
    GenerationRequest,
    GenerationResponse,
    HealthResponse,
    ProjectDetailResponse,
    ValidationSummarySchema,
)

__all__ = [
    "app",
    "create_app",
    "ProjectRegistry",
    "get_default_registry",
    "GenerationRequest",
    "GenerationResponse",
    "HealthResponse",
    "ProjectDetailResponse",
    "ValidationSummarySchema",
    "AlternativeSummarySchema",
    "ExportResponse",
]
