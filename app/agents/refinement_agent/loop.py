"""Refinement Loop coordinator for validation-driven iterative correction.

Coordinates the iterative cycle:
Architectural Design -> Geometry Engine -> Independent Validator -> Refinement Agent -> repeat
Enforces maximum iteration limits, oscillation detection, and hard constraint preservation.
"""

from __future__ import annotations
import hashlib
import json
from typing import Any, List, Optional, Set, Tuple

from app.agents.refinement_agent.agent import RefinementAgent
from app.agents.refinement_agent.context import RefinementContextBuilder
from app.geometry.engine import GeometryEngine
from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.planning import PlanningSpec
from app.models.refinement import (
    RefinementChange,
    RefinementIterationRecord,
    RefinementResult,
    RefinementStatus,
)
from app.models.requirements import Requirements
from app.models.validation import ValidationReport
from app.validation.validator import FloorPlanValidator

Point2D = Tuple[float, float]


class RefinementLoop:
    """Orchestrates the validation-driven architectural refinement loop."""

    def __init__(
        self,
        refinement_agent: Optional[RefinementAgent] = None,
        geometry_engine: Optional[GeometryEngine] = None,
        validator: Optional[FloorPlanValidator] = None,
        max_iterations: int = 3,
    ):
        """Initialize RefinementLoop.

        Args:
            refinement_agent: Optional RefinementAgent. Defaults to standard agent with mock.
            geometry_engine: Optional GeometryEngine. Defaults to new engine.
            validator: Optional FloorPlanValidator. Defaults to new validator.
            max_iterations: Maximum allowed refinement cycles (default: 3).
        """
        self.refinement_agent = refinement_agent or RefinementAgent()
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.validator = validator or FloorPlanValidator()
        self.max_iterations = max(1, max_iterations)

    def run(
        self,
        initial_design: ArchitecturalDesignSet,
        allocation_set: AllocationSet,
        requirements: Optional[Requirements] = None,
        planning_spec: Optional[PlanningSpec] = None,
        project_name: str = "",
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
        target_strategy: Optional[str] = None,
        initial_report: Optional[ValidationReport] = None,
        max_iterations: Optional[int] = None,
        **kwargs: Any,
    ) -> RefinementResult:
        """Execute the validation-driven refinement loop until valid or stopped.

        Args:
            initial_design: Initial ArchitecturalDesignSet from Architectural Agent.
            allocation_set: Authoritative ASAA AllocationSet.
            requirements: Upstream Requirements.
            planning_spec: Upstream PlanningSpec.
            project_name: Project name for identification.
            plot_boundary: Optional plot boundary.
            buildable_boundary: Optional buildable envelope.
            target_strategy: Optional architectural design strategy to preserve during refinement.
            initial_report: Optional pre-computed initial ValidationReport.
            max_iterations: Optional override for max refinement iterations.

        Returns:
            Authoritative RefinementResult tracking all iterations and final status.
        """
        iteration_records: list[RefinementIterationRecord] = []
        validation_reports: list[ValidationReport] = []
        all_changes: list[RefinementChange] = []
        visited_fingerprints: Set[str] = set()

        current_design = initial_design

        # Ensure boundaries are preserved from allocation_set if not explicitly passed
        if plot_boundary is None and allocation_set and getattr(allocation_set, "plot_boundary", None):
            plot_boundary = list(allocation_set.plot_boundary)
        if buildable_boundary is None and allocation_set and getattr(allocation_set, "buildable_boundary", None):
            buildable_boundary = list(allocation_set.buildable_boundary)

        # Infeasibility check: if allocation_set is missing or empty
        if not allocation_set or not allocation_set.allocations:
            return RefinementResult(
                status=RefinementStatus.INFEASIBLE_UNDER_CONSTRAINTS,
                initial_design=initial_design,
                final_design=current_design,
                iterations=[],
                validation_reports=[],
                changes=[],
                termination_reason="Infeasible requirements: no valid spatial allocations available",
            )

        # ------------------------------------------------------------------
        # Iteration 0: Initial Physical Construction and Validation
        # ------------------------------------------------------------------
        if initial_report is not None:
            current_report = initial_report
            current_floor_plan_set = kwargs.get("initial_floor_plan_set") or self.geometry_engine.construct(
                design_set=current_design,
                allocation_set=allocation_set,
                project_name=project_name,
                plot_boundary=plot_boundary,
                buildable_boundary=buildable_boundary,
            )
        else:
            current_floor_plan_set = self.geometry_engine.construct(
                design_set=current_design,
                allocation_set=allocation_set,
                project_name=project_name,
                plot_boundary=plot_boundary,
                buildable_boundary=buildable_boundary,
            )
            current_report = self.validator.validate(
                floor_plan_set=current_floor_plan_set,
                requirements=requirements,
                planning_spec=planning_spec,
                allocation_set=allocation_set,
                architectural_design_set=current_design,
                plot_boundary=plot_boundary,
                buildable_boundary=buildable_boundary,
                iteration=0,
            )

        initial_record = RefinementIterationRecord(
            iteration=0,
            design_version=current_design.version,
            error_count=current_report.total_errors,
            warning_count=current_report.total_warnings,
            score=current_report.overall_score,
            issue_ids=[i.id for i in current_report.all_issues()],
            changes=[],
            validation_status="valid" if current_report.overall_valid else "invalid",
            overall_valid=current_report.overall_valid,
        )
        iteration_records.append(initial_record)
        validation_reports.append(current_report)

        visited_fingerprints.add(self._compute_fingerprint(current_design))

        if current_report.overall_valid:
            return RefinementResult(
                status=RefinementStatus.VALID_ON_INITIAL_PASS,
                initial_design=initial_design,
                final_design=current_design,
                final_floor_plan_set=current_floor_plan_set,
                iterations=iteration_records,
                validation_reports=validation_reports,
                changes=[],
                termination_reason="Design was valid on initial pass without requiring refinement",
            )

        # Check for unrecoverable infeasibility reported by validator
        if any("exceeds available buildable area" in i.message.lower() or "deficit" in i.message.lower() for i in current_report.all_issues()):
            return RefinementResult(
                status=RefinementStatus.INFEASIBLE_UNDER_CONSTRAINTS,
                initial_design=initial_design,
                final_design=current_design,
                final_floor_plan_set=current_floor_plan_set,
                iterations=iteration_records,
                validation_reports=validation_reports,
                changes=[],
                termination_reason="Infeasible requirements: required room areas exceed available buildable area",
            )

        # ------------------------------------------------------------------
        # Iterative Refinement Cycles: 1 .. max_iterations
        # ------------------------------------------------------------------
        eff_max = max(1, max_iterations) if max_iterations is not None else self.max_iterations
        for iter_idx in range(1, eff_max + 1):
            refinement_context = RefinementContextBuilder.build(
                requirements=requirements or Requirements(),
                planning_spec=planning_spec or PlanningSpec(),
                allocation_set=allocation_set,
                current_design=current_design,
                validation_report=current_report,
                iteration=iter_idx,
                max_iterations=eff_max,
                previous_history=iteration_records,
                target_design_strategy=target_strategy,
            )

            # 1. Invoke Refinement Agent
            try:
                revised_design, iter_changes = self.refinement_agent.refine(refinement_context)
            except Exception as e:
                return RefinementResult(
                    status=RefinementStatus.REFINEMENT_OUTPUT_INVALID,
                    initial_design=initial_design,
                    final_design=current_design,
                    final_floor_plan_set=current_floor_plan_set,
                    iterations=iteration_records,
                    validation_reports=validation_reports,
                    changes=all_changes,
                    termination_reason=f"Refinement output failed contract validation: {e}",
                )

            all_changes.extend(iter_changes)
            revised_fingerprint = self._compute_fingerprint(revised_design)

            # 2. Oscillation / No-Change Detection
            if not iter_changes or revised_fingerprint == self._compute_fingerprint(current_design):
                return RefinementResult(
                    status=RefinementStatus.NO_CHANGE,
                    initial_design=initial_design,
                    final_design=current_design,
                    final_floor_plan_set=current_floor_plan_set,
                    iterations=iteration_records,
                    validation_reports=validation_reports,
                    changes=all_changes,
                    termination_reason="Refinement agent produced an unchanged design; stopping to prevent infinite loop (no_change)",
                )

            if revised_fingerprint in visited_fingerprints:
                return RefinementResult(
                    status=RefinementStatus.OSCILLATION,
                    initial_design=initial_design,
                    final_design=current_design,
                    final_floor_plan_set=current_floor_plan_set,
                    iterations=iteration_records,
                    validation_reports=validation_reports,
                    changes=all_changes,
                    termination_reason="Refinement agent entered an oscillatory cycle; stopping loop (oscillation)",
                )

            visited_fingerprints.add(revised_fingerprint)

            # 3. Physical Geometry Reconstruction
            new_floor_plan_set = self.geometry_engine.construct(
                design_set=revised_design,
                allocation_set=allocation_set,
                project_name=project_name,
                plot_boundary=plot_boundary,
                buildable_boundary=buildable_boundary,
            )

            # 4. Independent Validation
            new_report = self.validator.validate(
                floor_plan_set=new_floor_plan_set,
                requirements=requirements,
                planning_spec=planning_spec,
                allocation_set=allocation_set,
                architectural_design_set=revised_design,
                plot_boundary=plot_boundary,
                buildable_boundary=buildable_boundary,
                iteration=iter_idx,
            )

            iter_record = RefinementIterationRecord(
                iteration=iter_idx,
                design_version=revised_design.version,
                error_count=new_report.total_errors,
                warning_count=new_report.total_warnings,
                score=new_report.overall_score,
                issue_ids=[i.id for i in new_report.all_issues()],
                changes=iter_changes,
                validation_status="valid" if new_report.overall_valid else "invalid",
                overall_valid=new_report.overall_valid,
            )
            iteration_records.append(iter_record)
            validation_reports.append(new_report)

            current_design = revised_design
            current_floor_plan_set = new_floor_plan_set
            current_report = new_report

            # 5. Success Check
            if current_report.overall_valid:
                return RefinementResult(
                    status=RefinementStatus.VALID_AFTER_REFINEMENT,
                    initial_design=initial_design,
                    final_design=current_design,
                    final_floor_plan_set=current_floor_plan_set,
                    iterations=iteration_records,
                    validation_reports=validation_reports,
                    changes=all_changes,
                    termination_reason=f"Valid floor plan achieved after {iter_idx} refinement iteration(s)",
                )

        # ------------------------------------------------------------------
        # Max Iterations Reached Without Full Validity
        # ------------------------------------------------------------------
        return RefinementResult(
            status=RefinementStatus.MAX_ITERATIONS_REACHED,
            initial_design=initial_design,
            final_design=current_design,
            final_floor_plan_set=current_floor_plan_set,
            iterations=iteration_records,
            validation_reports=validation_reports,
            changes=all_changes,
            termination_reason=f"Reached maximum allowed refinement iterations ({self.max_iterations}) without resolving all errors",
        )

    @staticmethod
    def _compute_fingerprint(design_set: ArchitecturalDesignSet) -> str:
        """Compute a deterministic hash fingerprint of an ArchitecturalDesignSet."""
        canonical_elements = []
        for d in sorted(design_set.designs, key=lambda x: x.floor_number):
            for r in sorted(d.rooms, key=lambda x: x.id):
                doors_canon = sorted(
                    [(door.wall_orientation, door.connects_to, door.door_type) for door in r.doors]
                )
                windows_canon = sorted(
                    [(win.wall_orientation, getattr(win, "window_type", "standard")) for win in r.windows]
                )
                canonical_elements.append(
                    {
                        "floor": d.floor_number,
                        "room_id": r.id,
                        "shape": r.intended_shape,
                        "dims": [round(x, 2) for x in r.intended_dimensions] if r.intended_dimensions else [],
                        "doors": doors_canon,
                        "windows": windows_canon,
                    }
                )
        serialized = json.dumps(canonical_elements, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
