"""Data contracts and schemas for PlanForge research evaluation and benchmarking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from app.utils.ids import generate_id


class BenchmarkCategory(str, Enum):
    """Authoritative categorization tags for benchmark cases."""
    SINGLE_FLOOR = "SINGLE_FLOOR"
    MULTI_FLOOR = "MULTI_FLOOR"
    IRREGULAR_PLOT = "IRREGULAR_PLOT"
    TIGHT_SPACE = "TIGHT_SPACE"
    ADJACENCY_HEAVY = "ADJACENCY_HEAVY"
    SEPARATION_HEAVY = "SEPARATION_HEAVY"
    ATTACHED_SUITE = "ATTACHED_SUITE"
    STAIRCASE = "STAIRCASE"
    ORIENTATION = "ORIENTATION"
    INFEASIBLE = "INFEASIBLE"
    FEASIBILITY_EDGE_CASE = "FEASIBILITY_EDGE_CASE"


@dataclass
class BenchmarkCase:
    """A deterministic residential benchmark case."""
    case_id: str
    name: str
    description: str
    brief: str
    difficulty: str  # "low", "medium", "high"
    tags: List[BenchmarkCategory]
    expected_properties: Dict[str, Any] = field(default_factory=dict)

    def has_tag(self, tag: BenchmarkCategory | str) -> bool:
        """Check if case possesses given tag."""
        tag_val = tag.value if isinstance(tag, BenchmarkCategory) else str(tag)
        return any(t.value == tag_val for t in self.tags)


@dataclass
class MetricValue:
    """An individual evaluated metric with unit and availability status."""
    name: str
    value: Optional[float | int | str | bool]
    unit: str = ""
    is_available: bool = True
    unavailable_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "is_available": self.is_available,
            "unavailable_reason": self.unavailable_reason,
        }

    @classmethod
    def not_available(cls, name: str, reason: str, unit: str = "") -> MetricValue:
        """Helper to create an unavailable metric with an explicit explanation."""
        return cls(
            name=name,
            value=None,
            unit=unit,
            is_available=False,
            unavailable_reason=reason,
        )


@dataclass
class EvaluationConfig:
    """Configuration options governing an evaluation experiment run."""
    benchmark_case_ids: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    output_dir: str = "results/runs/latest"
    run_baseline: bool = True
    run_ablation: bool = True
    run_reproducibility: bool = True
    reproducibility_runs: int = 3
    export_plots: bool = True
    num_alternatives: int = 1
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_case_ids": self.benchmark_case_ids,
            "tags": self.tags,
            "output_dir": self.output_dir,
            "run_baseline": self.run_baseline,
            "run_ablation": self.run_ablation,
            "run_reproducibility": self.run_reproducibility,
            "reproducibility_runs": self.reproducibility_runs,
            "export_plots": self.export_plots,
            "num_alternatives": self.num_alternatives,
            "seed": self.seed,
        }


@dataclass
class CaseEvaluationResult:
    """Complete evaluation output for a single benchmark case run."""
    case_id: str
    name: str
    tags: List[str]
    status: str
    is_success: bool
    overall_valid: Optional[bool]
    error_message: Optional[str] = None
    metrics: Dict[str, MetricValue] = field(default_factory=dict)
    stage_timings_ms: Dict[str, float] = field(default_factory=dict)
    stage_statuses: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "tags": self.tags,
            "status": self.status,
            "is_success": self.is_success,
            "overall_valid": self.overall_valid,
            "error_message": self.error_message,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "stage_timings_ms": self.stage_timings_ms,
            "stage_statuses": self.stage_statuses,
        }


@dataclass
class AblationResult:
    """Comparative outcome between two pipeline configurations."""
    ablation_id: str
    case_id: str
    variant_a_name: str
    variant_a_metrics: Dict[str, Any]
    variant_b_name: str
    variant_b_metrics: Dict[str, Any]
    deltas: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ablation_id": self.ablation_id,
            "case_id": self.case_id,
            "variant_a_name": self.variant_a_name,
            "variant_a_metrics": self.variant_a_metrics,
            "variant_b_name": self.variant_b_name,
            "variant_b_metrics": self.variant_b_metrics,
            "deltas": self.deltas,
        }


@dataclass
class ReproducibilityResult:
    """Record of deterministic multi-run output comparison."""
    case_id: str
    num_runs: int
    is_identical: bool
    divergence_stage: Optional[str] = None
    hashes: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "num_runs": self.num_runs,
            "is_identical": self.is_identical,
            "divergence_stage": self.divergence_stage,
            "hashes": self.hashes,
            "details": self.details,
        }


@dataclass
class ExperimentRun:
    """Top-level aggregation of an entire experimental evaluation session."""
    run_id: str = field(default_factory=lambda: generate_id("eval_run"))
    timestamp: str = ""
    config: Optional[EvaluationConfig] = None
    case_results: List[CaseEvaluationResult] = field(default_factory=list)
    ablation_results: List[AblationResult] = field(default_factory=list)
    reproducibility_results: List[ReproducibilityResult] = field(default_factory=list)
    summary_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "config": self.config.to_dict() if self.config else {},
            "case_results": [c.to_dict() for c in self.case_results],
            "ablation_results": [a.to_dict() for a in self.ablation_results],
            "reproducibility_results": [r.to_dict() for r in self.reproducibility_results],
            "summary_metrics": self.summary_metrics,
        }
