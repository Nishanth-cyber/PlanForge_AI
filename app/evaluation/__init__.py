"""PlanForge Research Evaluation & Benchmarking Subsystem (Phase 13)."""

from app.evaluation.ablation import AblationStudyCoordinator
from app.evaluation.aggregation import MetricAggregator
from app.evaluation.baselines import BaselineSpatialAllocator
from app.evaluation.benchmark import BENCHMARK_CASES, BenchmarkCase, BenchmarkCategory, BenchmarkRegistry
from app.evaluation.errors import (
    BaselineAllocationError,
    BenchmarkExecutionError,
    EvaluationError,
    MetricComputationError,
    ReportGenerationError,
)
from app.evaluation.metrics import MetricCalculator
from app.evaluation.models import (
    AblationResult,
    CaseEvaluationResult,
    EvaluationConfig,
    ExperimentRun,
    MetricValue,
    ReproducibilityResult,
)
from app.evaluation.plotting import EvaluationPlotter
from app.evaluation.reporting import EvaluationReporter
from app.evaluation.reproducibility import ReproducibilityAuditor
from app.evaluation.runner import BenchmarkRunner

__all__ = [
    "AblationResult",
    "AblationStudyCoordinator",
    "BENCHMARK_CASES",
    "BaselineAllocationError",
    "BaselineSpatialAllocator",
    "BenchmarkCase",
    "BenchmarkCategory",
    "BenchmarkExecutionError",
    "BenchmarkRegistry",
    "BenchmarkRunner",
    "CaseEvaluationResult",
    "EvaluationConfig",
    "EvaluationError",
    "EvaluationPlotter",
    "EvaluationReporter",
    "ExperimentRun",
    "MetricAggregator",
    "MetricCalculator",
    "MetricComputationError",
    "MetricValue",
    "ReportGenerationError",
    "ReproducibilityAuditor",
    "ReproducibilityResult",
]
