"""Consolidated PipelineResult representing the complete outcome of a PlanForge pipeline run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.requirement_agent.completeness_gate import CompletenessResult
from app.explainability.models import DecisionTrace
from app.export.integrity import ExportIntegrityReport
from app.models.allocation import AllocationSet
from app.models.alternatives import DesignAlternativeSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.planning import PlanningSpec
from app.models.refinement import RefinementResult
from app.models.requirements import Requirements
from app.models.validation import ValidationReport
from app.orchestration.state import StageRecord


@dataclass
class PipelineResult:
    """Structured result returned by the PlanForge orchestrator."""
    project_id: str
    project_name: str = ""
    status: str = "completed"  # "completed", "incomplete_requirements", "failed", "partial"

    # Domain artifacts produced during generation
    requirements: Optional[Requirements] = None
    completeness_result: Optional[CompletenessResult] = None
    planning_spec: Optional[PlanningSpec] = None
    allocation_set: Optional[AllocationSet] = None
    architectural_design_set: Optional[ArchitecturalDesignSet] = None
    floor_plan_set: Optional[FloorPlanSet] = None
    validation_report: Optional[ValidationReport] = None
    refinement_result: Optional[RefinementResult] = None
    alternative_set: Optional[DesignAlternativeSet] = None
    decision_trace: Optional[DecisionTrace] = None
    export_bundle_path: Optional[str] = None
    export_integrity_report: Optional[ExportIntegrityReport] = None

    # Lifecycle tracking & diagnostics
    stage_records: Dict[str, StageRecord] = field(default_factory=dict)
    error_message: Optional[str] = None
    missing_fields: List[str] = field(default_factory=list)
    missing_floors: List[int] = field(default_factory=list)
    clarification_questions: List[str] = field(default_factory=list)
    agentic_state: Optional[Dict[str, Any]] = None
    decisions: Optional[List[Dict[str, Any]]] = None

    @property
    def is_success(self) -> bool:
        """True if the generation completed successfully."""
        return self.status == "completed"

    @property
    def is_valid(self) -> bool:
        """True if validation report exists and indicates overall validity."""
        if self.validation_report:
            return self.validation_report.overall_valid
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to structured dictionary representation."""
        res: Dict[str, Any] = {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "status": self.status,
            "is_success": self.is_success,
            "is_valid": self.is_valid,
            "stage_statuses": {k: v.status.value for k, v in self.stage_records.items()},
            "export_bundle_path": self.export_bundle_path,
            "decision_trace_available": self.decision_trace is not None,
            "error_message": self.error_message,
            "agentic_state": self.agentic_state,
            "decisions": self.decisions,
        }

        if self.completeness_result and not self.completeness_result.is_complete:
            res["missing_fields"] = self.completeness_result.missing_fields
            res["missing_floors"] = self.completeness_result.missing_floors
            res["clarification_questions"] = self.completeness_result.clarification_questions

        if self.validation_report:
            res["validation_summary"] = {
                "overall_valid": self.validation_report.overall_valid,
                "overall_score": round(self.validation_report.overall_score, 2),
                "total_errors": self.validation_report.total_errors,
                "total_warnings": self.validation_report.total_warnings,
            }

        if self.alternative_set and self.alternative_set.alternatives:
            res["alternatives"] = [
                {
                    "alternative_id": alt.alternative_id,
                    "index": alt.index,
                    "strategy": alt.strategy,
                    "is_valid": alt.is_valid,
                    "characteristics": list(alt.characteristics),
                    "diversity_scores": dict(alt.diversity_scores),
                }
                for alt in self.alternative_set.alternatives
            ]
        elif self.floor_plan_set:
            res["alternatives"] = [
                {
                    "alternative_id": "primary",
                    "index": 1,
                    "strategy": "standard",
                    "is_valid": self.floor_plan_set.all_valid,
                    "characteristics": ["Primary constructed floor plan"],
                    "diversity_scores": {},
                }
            ]

        return res
