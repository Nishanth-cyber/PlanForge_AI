"""Unit tests for RefinementContext and issue prioritization."""

import pytest
from app.agents.refinement_agent.context import (
    RefinementContext,
    RefinementContextBuilder,
)
from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult


def test_refinement_context_creation_and_immutability():
    """Verify RefinementContext is frozen and immutable."""
    reqs = Requirements()
    plan_spec = PlanningSpec()
    alloc_set = AllocationSet()
    design_set = ArchitecturalDesignSet()
    report = ValidationReport()

    ctx = RefinementContextBuilder.build(
        requirements=reqs,
        planning_spec=plan_spec,
        allocation_set=alloc_set,
        current_design=design_set,
        validation_report=report,
        iteration=1,
        max_iterations=3,
    )

    assert ctx.iteration == 1
    assert ctx.max_iterations == 3
    with pytest.raises(Exception):
        # dataclass frozen=True forbids attribute assignment
        ctx.iteration = 2  # type: ignore


def test_issue_prioritization():
    """Verify issues are prioritized: errors before warnings, then by category priority."""
    res = ValidationResult(floor_number=1, is_valid=False)
    # Add issues in arbitrary order
    res.add_issue(ValidationIssue(severity="warning", category="window", check="window_orientation"))
    res.add_issue(ValidationIssue(severity="error", category="door", check="floating_door"))
    res.add_issue(ValidationIssue(severity="error", category="completeness", check="missing_room"))
    res.add_issue(ValidationIssue(severity="error", category="boundary", check="plot_spill"))
    res.add_issue(ValidationIssue(severity="warning", category="dimension", check="target_undersize"))

    report = ValidationReport(results=[res])
    ctx = RefinementContextBuilder.build(
        requirements=Requirements(),
        planning_spec=PlanningSpec(),
        allocation_set=AllocationSet(),
        current_design=ArchitecturalDesignSet(),
        validation_report=report,
    )

    prioritized = ctx.get_prioritized_floor_issues(1)
    # Check that all errors precede all warnings
    severities = [i.severity for i in prioritized]
    assert severities == ["error", "error", "error", "warning", "warning"]

    # Check category order among errors: completeness (1) -> boundary (2) -> door (8)
    error_cats = [i.category for i in prioritized if i.severity == "error"]
    assert error_cats == ["completeness", "boundary", "door"]


def test_format_floor_diagnostics():
    """Verify structured textual diagnostics generation for prompt injection."""
    res = ValidationResult(floor_number=1, is_valid=False)
    res.add_issue(
        ValidationIssue(
            severity="error",
            category="door",
            check="floating_door",
            message="Door has no wall",
            room_id="living_01",
            details={"distance": 0.5},
        )
    )
    report = ValidationReport(results=[res])
    ctx = RefinementContextBuilder.build(
        requirements=Requirements(),
        planning_spec=PlanningSpec(),
        allocation_set=AllocationSet(),
        current_design=ArchitecturalDesignSet(),
        validation_report=report,
    )

    diag = ctx.format_floor_diagnostics(1)
    assert "HARD VALIDATION ERRORS (1)" in diag
    assert "[DOOR] floating_door [Room: living_01]: Door has no wall" in diag
    assert "distance=0.5" in diag
