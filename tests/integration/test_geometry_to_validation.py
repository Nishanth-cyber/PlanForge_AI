"""Integration test connecting Geometry Engine outputs to Independent Validator.

Verifies:
GeometryEngine (Phase 6)
       ↓
FloorPlanSet (unvalidated: is_valid=False, validation=None)
       ↓
FloorPlanValidator (Phase 7)
       ↓
ValidationReport (authoritative verification: score, issues, checks_passed, is_valid updated)
"""

from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.models.validation import ValidationReport
from app.validation.validator import FloorPlanValidator, Validator


def test_geometry_to_validator_integration():
    """Verify that a FloorPlanSet produced by GeometryEngine is successfully verified by FloorPlanValidator."""
    brief = """
    Design a 2-floor villa on a 40 feet by 50 feet plot with 2m setbacks.
    Floor 1:
    - 1 living room of 200 sq ft
    - 1 dining room of 120 sq ft
    - 1 kitchen of 100 sq ft
    - 1 bedroom of 120 sq ft
    - 1 bathroom of 50 sq ft
    - staircase to upper floor
    Floor 2:
    - 1 master bedroom of 180 sq ft with attached bathroom of 50 sq ft
    - 1 bedroom of 120 sq ft
    - 1 bathroom of 50 sq ft
    """

    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Geometry-to-Validation Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    design_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
    )

    geo_engine = GeometryEngine()
    floor_plan_set = geo_engine.construct(
        design_set=design_set,
        allocation_set=allocation_set,
        project_name="Geometry-to-Validation Test",
    )

    # Invariant: Prior to validation, floor plans are unvalidated
    for fp in floor_plan_set.floor_plans:
        assert fp.is_valid is False
        assert fp.validation is None
    assert floor_plan_set.validation_report is None

    # Execute Independent Validator
    validator = FloorPlanValidator()
    report = validator.validate(
        floor_plan_set=floor_plan_set,
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=design_set,
    )

    # Invariant: Validation report assigned and floor plan states updated
    assert isinstance(report, ValidationReport)
    assert floor_plan_set.validation_report is report
    assert len(report.results) == 2

    for fp in floor_plan_set.floor_plans:
        assert fp.validation is not None
        assert fp.is_valid == fp.validation.is_valid
        assert fp.validation.score >= 0.0

    # Ensure categories are evaluated
    for res in report.results:
        assert len(res.checks_passed) > 0
        assert "boundary" in res.checks_passed or "boundary" in res.checks_failed
