"""Refinement Context and validation issue prioritization.

Constructs an immutable context bundling:
- Upstream authoritative Requirements, PlanningSpec, AllocationSet
- Current ArchitecturalDesignSet proposal
- Structured ValidationReport with prioritized issue diagnostics
- Refinement iteration history
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.planning import PlanningSpec
from app.models.refinement import RefinementIterationRecord
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport

CATEGORY_PRIORITY = {
    "completeness": 1,
    "boundary": 2,
    "allocation": 3,
    "dimension": 4,
    "relationship": 5,
    "staircase": 6,
    "multi_floor": 6,
    "connectivity": 7,
    "circulation": 7,
    "door": 8,
    "window": 9,
}


@dataclass(frozen=True)
class RefinementContext:
    """Immutable context provided to the Refinement Agent for a refinement pass."""
    requirements: Requirements
    planning_spec: PlanningSpec
    allocation_set: AllocationSet
    current_design: ArchitecturalDesignSet
    validation_report: ValidationReport
    iteration: int = 1
    max_iterations: int = 3
    previous_history: tuple[RefinementIterationRecord, ...] = field(default_factory=tuple)
    target_design_strategy: Optional[str] = None

    def get_floor_issues(self, floor_number: int) -> list[ValidationIssue]:
        """Retrieve all validation issues reported for a specific floor."""
        floor_result = self.validation_report.get_result(floor_number)
        if not floor_result:
            return []
        return list(floor_result.issues)

    def get_prioritized_floor_issues(self, floor_number: int) -> list[ValidationIssue]:
        """Return floor issues sorted deterministically by severity and architectural priority."""
        issues = self.get_floor_issues(floor_number)

        def sort_key(issue: ValidationIssue) -> tuple[int, int, str]:
            # Severity: errors (0) before warnings (1)
            sev_rank = 0 if issue.severity == "error" else 1
            # Category priority
            cat_rank = CATEGORY_PRIORITY.get(issue.category, 10)
            return (sev_rank, cat_rank, issue.check)

        return sorted(issues, key=sort_key)

    def format_floor_diagnostics(self, floor_number: int) -> str:
        """Format prioritized validation issues into structured LLM diagnostic prompt text."""
        prioritized = self.get_prioritized_floor_issues(floor_number)
        if not prioritized:
            return "No validation issues reported for this floor."

        lines: list[str] = []
        errors = [i for i in prioritized if i.severity == "error"]
        warnings = [i for i in prioritized if i.severity == "warning"]

        if errors:
            lines.append(f"### HARD VALIDATION ERRORS ({len(errors)}) - MUST BE FIXED:")
            for idx, err in enumerate(errors, 1):
                target_str = f" [Room: {err.room_id}]" if err.room_id else ""
                lines.append(f"  {idx}. [{err.category.upper()}] {err.check}{target_str}: {err.message}")
                if err.details:
                    details_str = ", ".join(f"{k}={v}" for k, v in err.details.items())
                    lines.append(f"     Details: {details_str}")

        if warnings:
            lines.append(f"\n### ADVISORY WARNINGS ({len(warnings)}) - ADDRESS IF POSSIBLE:")
            for idx, warn in enumerate(warnings, 1):
                target_str = f" [Room: {warn.room_id}]" if warn.room_id else ""
                lines.append(f"  {idx}. [{warn.category.upper()}] {warn.check}{target_str}: {warn.message}")
                if warn.details:
                    details_str = ", ".join(f"{k}={v}" for k, v in warn.details.items())
                    lines.append(f"     Details: {details_str}")

        return "\n".join(lines)


class RefinementContextBuilder:
    """Builder for constructing immutable RefinementContext instances."""

    @staticmethod
    def build(
        requirements: Requirements,
        planning_spec: PlanningSpec,
        allocation_set: AllocationSet,
        current_design: ArchitecturalDesignSet,
        validation_report: ValidationReport,
        iteration: int = 1,
        max_iterations: int = 3,
        previous_history: Optional[list[RefinementIterationRecord]] = None,
        target_design_strategy: Optional[str] = None,
    ) -> RefinementContext:
        """Construct an immutable RefinementContext."""
        history_tuple = tuple(previous_history) if previous_history else ()
        return RefinementContext(
            requirements=requirements,
            planning_spec=planning_spec,
            allocation_set=allocation_set,
            current_design=current_design,
            validation_report=validation_report,
            iteration=iteration,
            max_iterations=max_iterations,
            previous_history=history_tuple,
            target_design_strategy=target_design_strategy,
        )
