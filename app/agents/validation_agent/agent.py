"""Validation Agent for PlanForge AI.

Wraps the authoritative deterministic FloorPlanValidator and provides an agentic
interpretation layer that categorizes findings, identifies root causes,
assesses remediability, and prescribes actionable corrective strategies
to the Planning and Refinement agents.

Invariants:
1. Deterministic authority: Hard errors can NEVER be overridden by LLM or heuristics.
2. Machine-readable diagnostics: Every issue is paired with severity, affected entities,
   evidence, and suggested corrective actions.
3. Clean separation: Hard errors prevent final plan acceptance; soft warnings provide guidance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.agentic.state import Finding
from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport
from app.validation.validator import FloorPlanValidator

logger = logging.getLogger(__name__)

Point2D = Tuple[float, float]


@dataclass
class ValidationAnalysis:
    """Rich interpretation of validation results for autonomous agent decision-making."""

    report: ValidationReport
    findings: List[Finding] = field(default_factory=list)
    hard_error_count: int = 0
    warning_count: int = 0
    is_valid: bool = False
    score: float = 0.0
    primary_failure_category: Optional[str] = None
    suggested_strategy: str = "none"  # "none" | "refine_geometry" | "reallocate_asaa" | "replan_zoning" | "declare_infeasible"
    remediable: bool = True
    infeasibility_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "hard_error_count": self.hard_error_count,
            "warning_count": self.warning_count,
            "primary_failure_category": self.primary_failure_category,
            "suggested_strategy": self.suggested_strategy,
            "remediable": self.remediable,
            "infeasibility_reason": self.infeasibility_reason,
            "findings_count": len(self.findings),
        }


class ValidationAgent:
    """Authoritative agent for floor plan verification, issue diagnosis, and remediation prescription."""

    def __init__(self, validator: Optional[FloorPlanValidator] = None) -> None:
        self.validator = validator or FloorPlanValidator()

    def validate(
        self,
        floor_plan_set: FloorPlanSet,
        requirements: Optional[Requirements] = None,
        planning_spec: Optional[PlanningSpec] = None,
        allocation_set: Optional[AllocationSet] = None,
        architectural_design_set: Optional[ArchitecturalDesignSet] = None,
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
        iteration: int = 0,
    ) -> ValidationAnalysis:
        """Execute deterministic validation and produce structured agentic analysis."""
        report = self.validator.validate(
            floor_plan_set=floor_plan_set,
            requirements=requirements,
            planning_spec=planning_spec,
            allocation_set=allocation_set,
            architectural_design_set=architectural_design_set,
            plot_boundary=plot_boundary,
            buildable_boundary=buildable_boundary,
            iteration=iteration,
        )

        findings: List[Finding] = []
        for issue in report.all_issues():
            f = self._issue_to_finding(issue)
            findings.append(f)

        hard_errors = [f for f in findings if f.hard]
        warnings = [f for f in findings if not f.hard]

        primary_category, strategy, remediable, infeas_reason = self._diagnose(
            hard_errors, warnings, requirements, plot_boundary, buildable_boundary
        )

        return ValidationAnalysis(
            report=report,
            findings=findings,
            hard_error_count=len(hard_errors),
            warning_count=len(warnings),
            is_valid=report.overall_valid,
            score=report.overall_score,
            primary_failure_category=primary_category,
            suggested_strategy=strategy,
            remediable=remediable,
            infeasibility_reason=infeas_reason,
        )

    def _issue_to_finding(self, issue: ValidationIssue) -> Finding:
        actions = self._prescribe_actions(issue)
        return Finding(
            code=issue.category or issue.check or "unknown",
            severity=issue.severity or "error",
            message=issue.message or "",
            target=issue.target_id or issue.room_id,
            floor=issue.floor_number,
            suggested_actions=actions,
            evidence=issue.details or {},
            id=issue.id,
        )

    @staticmethod
    def _prescribe_actions(issue: ValidationIssue) -> List[str]:
        cat = (issue.category or "").lower()
        msg = (issue.message or "").lower()

        if "overlap" in cat or "overlap" in msg:
            return ["refine_door_window_offsets", "nudge_room_geometry", "reallocate_asaa"]
        if "boundary" in cat or "containment" in msg:
            return ["clamp_to_boundary", "reallocate_asaa_aspect_ratio"]
        if "dimension" in cat or "area" in msg:
            return ["adjust_room_aspect_ratio", "reallocate_spatial_budget"]
        if "connectivity" in cat or "isolated" in msg or "circulation" in msg:
            return ["add_connecting_door", "reorient_room_access", "replan_circulation"]
        if "relationship" in cat or "adjacency" in msg:
            return ["swap_room_positions", "replan_zoning"]
        if "staircase" in cat:
            return ["realign_staircase_core", "replan_multi_floor"]
        if "door" in cat:
            return ["reposition_door", "adjust_wall_placement"]
        if "window" in cat:
            return ["reposition_window", "adjust_exterior_exposure"]
        return ["refine_design"]

    def _diagnose(
        self,
        hard_errors: List[Finding],
        warnings: List[Finding],
        requirements: Optional[Requirements],
        plot_boundary: Optional[List[Point2D]],
        buildable_boundary: Optional[List[Point2D]],
    ) -> Tuple[Optional[str], str, bool, Optional[str]]:
        if not hard_errors:
            return None, "none", True, None

        # Count errors per category
        cat_counts: Dict[str, int] = {}
        for err in hard_errors:
            cat_counts[err.code] = cat_counts.get(err.code, 0) + 1

        primary = max(cat_counts.items(), key=lambda x: x[1])[0] if cat_counts else "unknown"

        # Check for unrecoverable infeasibility
        for err in hard_errors:
            msg = err.message.lower()
            if "exceeds available buildable area" in msg or "deficit" in msg:
                return (
                    primary,
                    "declare_infeasible",
                    False,
                    f"Required space exceeds envelope: {err.message}",
                )

        # Strategic recommendation based on primary failure
        if primary in {"overlap", "door", "window"}:
            return primary, "refine_geometry", True, None
        elif primary in {"boundary", "dimension"}:
            return primary, "reallocate_asaa", True, None
        elif primary in {"connectivity", "circulation", "relationship", "staircase"}:
            return primary, "replan_zoning", True, None
        else:
            return primary, "refine_geometry", True, None
