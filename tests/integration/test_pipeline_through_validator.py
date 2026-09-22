"""Full end-to-end pipeline integration test through Phase 7 (Validator).

Pipeline flow:
Requirements (Phase 2)
       ↓
Planning Agent (Phase 3)
       ↓
ASAA Allocator (Phase 4)
       ↓
Architectural LLM Agent (Phase 5)
       ↓
Geometry Engine (Phase 6)
       ↓
Independent Validator (Phase 7)
       ↓
ValidationReport (authoritative verification across all 18 check groups)
"""

import pytest
from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.models.validation import ValidationReport
from app.validation.validator import FloorPlanValidator, Validator


def test_full_pipeline_through_validator():
    """Verify complete pipeline execution from raw text requirements through independent validation."""
    brief = """
    Design a 2-floor house on a 30 feet by 40 feet plot with 2m setbacks.
    Floor 1:
    - 1 large living room of 200 sq ft next to dining
    - 1 dining room of 120 sq ft next to kitchen
    - 1 kitchen of 100 sq ft
    - 1 guest bedroom of 120 sq ft
    - 1 common bathroom of 45 sq ft
    - staircase to upper floor
    Floor 2:
    - 1 master bedroom of 180 sq ft with attached bathroom of 50 sq ft
    - 1 bedroom of 120 sq ft
    - 1 study room of 90 sq ft
    - 1 common bathroom of 45 sq ft
    """

    # 1. Requirement Agent (Phase 2)
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Villa Harmony")

    # 2. Planning Agent (Phase 3)
    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    # 3. ASAA Allocator (Phase 4)
    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    # 4. Architectural Agent (Phase 5)
    arch_agent = ArchitecturalAgent()
    design_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
    )

    # 5. Geometry Engine (Phase 6)
    geo_engine = GeometryEngine()
    floor_plan_set = geo_engine.construct(
        design_set=design_set,
        allocation_set=allocation_set,
        project_name="Villa Harmony",
    )

    # Invariant: Prior to validation, floor plans are unvalidated
    for fp in floor_plan_set.floor_plans:
        assert fp.is_valid is False
        assert fp.validation is None

    # 6. Independent Validator (Phase 7)
    validator = Validator()
    report = validator.validate(
        floor_plan_set=floor_plan_set,
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=design_set,
    )

    # Assertions on ValidationReport
    assert isinstance(report, ValidationReport)
    assert floor_plan_set.validation_report is report
    assert len(report.results) == 2

    # Determinism: Repeating validation produces identical report metrics
    report2 = validator.validate(
        floor_plan_set=floor_plan_set,
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=design_set,
    )
    assert report.overall_score == report2.overall_score
    assert report.total_errors == report2.total_errors
    assert report.total_warnings == report2.total_warnings


def test_validator_catches_intentional_boundary_corruption():
    """Verify that an intentional boundary violation introduced into geometry is caught and invalidates the plan."""
    brief = """
    Design a 1-floor cottage on a 30 feet by 30 feet plot with 1.5m setbacks.
    Floor 1:
    - 1 living room of 150 sq ft
    - 1 bedroom of 100 sq ft
    - 1 bathroom of 40 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Cottage Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=12)
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
        project_name="Cottage Test",
    )

    # Corrupt Floor 1: Move a room way outside the plot boundary
    fp1 = floor_plan_set.get_floor_plan(1)
    corrupted_room = fp1.geometry.rooms[0]
    # Shift polygon coordinates by +50 meters outside
    shifted_poly = [(x + 50.0, y + 50.0) for (x, y) in corrupted_room.usable_polygon]
    corrupted_room.usable_polygon = shifted_poly
    corrupted_room.built_polygon = shifted_poly

    validator = FloorPlanValidator()
    report = validator.validate(
        floor_plan_set=floor_plan_set,
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=design_set,
    )

    assert report.overall_valid is False
    assert fp1.is_valid is False
    assert report.total_errors > 0

    issues = report.all_issues()
    boundary_errors = [i for i in issues if i.category == "boundary"]
    assert len(boundary_errors) > 0
    assert any("extends outside" in i.message for i in boundary_errors)


def test_validator_catches_intentional_isolation_corruption():
    """Verify that removing all doors to a room causes an isolated_room hard error."""
    brief = """
    Design a 1-floor house on a 30 feet by 30 feet plot with 1.5m setbacks.
    Floor 1:
    - 1 living room of 150 sq ft
    - 1 bedroom of 100 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Isolation Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=12)
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
        project_name="Isolation Test",
    )

    # Remove all doors from the floor plan geometry
    fp1 = floor_plan_set.get_floor_plan(1)
    fp1.geometry.doors = []

    validator = FloorPlanValidator()
    report = validator.validate(
        floor_plan_set=floor_plan_set,
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=design_set,
    )

    assert report.overall_valid is False
    assert fp1.is_valid is False

    issues = report.all_issues()
    isolation_errors = [i for i in issues if i.check == "isolated_room"]
    assert len(isolation_errors) > 0
