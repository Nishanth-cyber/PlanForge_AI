"""Evaluation-specific exception types for PlanForge research evaluation."""

from __future__ import annotations


class EvaluationError(Exception):
    """Base exception for all research evaluation errors."""
    pass


class BenchmarkExecutionError(EvaluationError):
    """Raised when a benchmark case execution fails unexpectedly."""
    pass


class MetricComputationError(EvaluationError):
    """Raised when metric calculation fails due to inconsistent or corrupt artifacts."""
    pass


class BaselineAllocationError(EvaluationError):
    """Raised when the baseline allocator cannot produce a feasible geometric partition."""
    pass


class ReportGenerationError(EvaluationError):
    """Raised when serialization or report formatting fails."""
    pass
