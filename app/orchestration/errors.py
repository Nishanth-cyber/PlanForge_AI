"""Structured exception hierarchy for PlanForge pipeline orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class OrchestrationError(Exception):
    """Base exception for all orchestration failures."""

    def __init__(self, message: str, project_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.project_id = project_id

    def __str__(self) -> str:
        if self.project_id:
            return f"[{self.project_id}] {self.message}"
        return self.message


class StageExecutionError(OrchestrationError):
    """Raised when a specific pipeline stage encounters an unrecoverable error."""

    def __init__(
        self,
        stage_name: str,
        message: str,
        project_id: Optional[str] = None,
        underlying_error: Optional[Exception] = None,
    ):
        super().__init__(f"Stage '{stage_name}' failed: {message}", project_id=project_id)
        self.stage_name = stage_name
        self.underlying_error = underlying_error


class IncompleteRequirementsError(OrchestrationError):
    """Raised when the requirement completeness gate determines requirements are insufficient."""

    def __init__(
        self,
        missing_fields: Optional[List[str]] = None,
        missing_floors: Optional[List[int]] = None,
        clarification_questions: Optional[List[str]] = None,
        message: str = "Requirements are incomplete and cannot proceed to spatial planning.",
        project_id: Optional[str] = None,
    ):
        super().__init__(message, project_id=project_id)
        self.missing_fields = missing_fields or []
        self.missing_floors = missing_floors or []
        self.clarification_questions = clarification_questions or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "incomplete_requirements",
            "message": self.message,
            "missing_fields": self.missing_fields,
            "missing_floors": self.missing_floors,
            "clarification_questions": self.clarification_questions,
        }


class PipelineConfigurationError(OrchestrationError):
    """Raised when orchestrator is misconfigured or initialized with invalid parameters."""
    pass
