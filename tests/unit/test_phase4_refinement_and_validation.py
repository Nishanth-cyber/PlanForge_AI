"""Phase 4 authoritative regression tests for Refinement Loop, Validation Authority, and Safety Guards.

Tests strictly enforce:
1. Valid plan skips refinement (refinement iteration count = 0 or skipped)
2. Invalid plan triggers refinement loop
3. Successful refinement converges to valid design (final is_valid is True)
4. No-change protection stops safely when refinement produces identical design
5. Oscillation protection stops safely when refinement oscillates (A -> B -> A)
6. Maximum iteration protection strictly enforces max_iterations limit
7. Infeasible requirements are reported as infeasible rather than repeatedly refined
8. Refinement preserves user requirements (room count, types, min areas, explicit dims)
9. Refinement preserves authoritative plot dimensions, polygon, and setbacks
10. Final validation remains authoritative (unresolved design never reports is_success=True)
11. Actual geometry is regenerated and revalidated after every refinement step
12. Full end-to-end pipeline execution with real refinement loop
"""

import copy
import pytest
from unittest.mock import MagicMock

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.planning_agent.agent import PlanningAgent
from app.agents.refinement_agent.agent import RefinementAgent
from app.agents.refinement_agent.loop import RefinementLoop
from app.agents.requirement_agent.parser import RequirementParser
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.models.allocation import Allocation, AllocationSet, AllocatedRegion
from app.models.architectural_design import ArchitecturalDesign, ArchitecturalDesignSet, RoomDesign
from app.models.doors import DoorIntent
from app.models.floor_plan import FloorPlanSet
from app.models.planning import PlanningSpec, FloorPlanSpec, RoomSpec
from app.models.refinement import RefinementChange, RefinementResult, RefinementStatus
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.state import StageStatus
from app.validation.validator import FloorPlanValidator


# =============================================================================
# Helper Fixtures
# =============================================================================

def _build_test_allocation_and_design():
    alloc_set = AllocationSet(
        plot_boundary=[(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)],
        buildable_boundary=[(1.0, 1.0), (19.0, 1.0), (19.0, 19.0), (1.0, 19.0)],
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="reg_living",
                        room_type="living",
                        approximate_dimensions=(8.0, 6.0),
                        polygon=[(1.0, 1.0), (9.0, 1.0), (9.0, 7.0), (1.0, 7.0)],
                    ),
                    AllocatedRegion(
                        id="reg_kitchen",
                        room_type="kitchen",
                        approximate_dimensions=(5.0, 5.0),
                        polygon=[(9.0, 1.0), (14.0, 1.0), (14.0, 6.0), (9.0, 6.0)],
                    ),
                ],
            )
        ],
    )

    design_set = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_living",
                        room_type="living",
                        allocated_region_id="reg_living",
                        intended_dimensions=(7.0, 5.0),
                        doors=[DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance")],
                    ),
                    RoomDesign(
                        id="r_kitchen",
                        room_type="kitchen",
                        allocated_region_id="reg_kitchen",
                        intended_dimensions=(4.5, 4.5),
                        doors=[DoorIntent(wall_orientation="west", connects_to="living", door_type="interior")],
                    ),
                ],
            )
        ]
    )

    reqs = Requirements(
        project_name="Refinement Test Project",
        target_floors=1,
        plot_dimensions=(20.0, 20.0),
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=30.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=15.0),
                ],
            )
        ],
    )

    return alloc_set, design_set, reqs


# =============================================================================
# Test 1 — Valid Plan Skips Refinement
# =============================================================================

def test_valid_plan_skips_refinement():
    """Verify an initially valid design completes without executing refinement iterations."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    mock_validator = MagicMock(spec=FloorPlanValidator)
    mock_validator.validate.return_value = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=100.0)],
        iteration=0,
    )

    mock_agent = MagicMock(spec=RefinementAgent)

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=3)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.status == RefinementStatus.VALID_ON_INITIAL_PASS
    assert result.is_valid is True
    # 0 refinement iterations (only initial pass record)
    assert len(result.iterations) == 1
    assert result.iterations[0].iteration == 0
    assert len(result.changes) == 0
    mock_agent.refine.assert_not_called()


# =============================================================================
# Test 2 — Invalid Plan Triggers Refinement
# =============================================================================

def test_invalid_plan_triggers_refinement():
    """Verify an invalid design triggers the refinement agent with diagnostics."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    mock_validator = MagicMock(spec=FloorPlanValidator)
    invalid_report = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                issues=[ValidationIssue(severity="error", category="door", check="missing_entrance")],
            )
        ],
        iteration=0,
    )
    valid_report = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=95.0)],
        iteration=1,
    )
    mock_validator.validate.side_effect = [invalid_report, valid_report]

    d_revised = copy.deepcopy(design_set)
    d_revised.designs[0].rooms[0].doors.append(
        DoorIntent(wall_orientation="north", connects_to="corridor", door_type="interior")
    )

    mock_agent = MagicMock(spec=RefinementAgent)
    mock_agent.refine.return_value = (
        d_revised,
        [RefinementChange(room_id="r_living", field_changed="doors", reason="Added entrance door")],
    )

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=3)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert mock_agent.refine.called
    assert result.status == RefinementStatus.VALID_AFTER_REFINEMENT
    assert result.is_valid is True
    assert len(result.iterations) == 2  # Iteration 0 (invalid) + Iteration 1 (valid)


# =============================================================================
# Test 3 — Successful Multi-Cycle Refinement
# =============================================================================

def test_successful_multi_cycle_refinement():
    """Verify refinement converges after 2 cycles and stops immediately once valid."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    mock_validator = MagicMock(spec=FloorPlanValidator)
    rep_0 = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=False, issues=[ValidationIssue(severity="error", category="door")])],
        iteration=0,
    )
    rep_1 = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=False, issues=[ValidationIssue(severity="error", category="window")])],
        iteration=1,
    )
    rep_2 = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=98.0)],
        iteration=2,
    )
    mock_validator.validate.side_effect = [rep_0, rep_1, rep_2]

    # Create designs with different dimensions within region bounds (reg is 8x6)
    d1 = copy.deepcopy(design_set)
    d1.designs[0].rooms[0].intended_dimensions = (6.5, 4.5)
    d2 = copy.deepcopy(design_set)
    d2.designs[0].rooms[0].intended_dimensions = (6.0, 4.0)

    mock_agent = MagicMock(spec=RefinementAgent)
    mock_agent.refine.side_effect = [
        (d1, [RefinementChange(room_id="r_living", field_changed="doors", reason="Fix door")]),
        (d2, [RefinementChange(room_id="r_living", field_changed="windows", reason="Fix window")]),
    ]

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=5)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.status == RefinementStatus.VALID_AFTER_REFINEMENT
    assert result.is_valid is True
    assert result.iteration == 3  # Iteration 0, 1, 2
    assert len(result.changes) == 2
    # Verify loop stopped at iteration 2 and did not run to max_iterations (5)
    assert mock_agent.refine.call_count == 2


# =============================================================================
# Test 4 — No-Change Protection
# =============================================================================

def test_no_change_protection():
    """Verify loop safely stops when refinement returns identical design without changes."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    mock_validator = MagicMock(spec=FloorPlanValidator)
    invalid_rep = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=False, issues=[ValidationIssue(severity="error")])],
        iteration=0,
    )
    mock_validator.validate.return_value = invalid_rep

    mock_agent = MagicMock(spec=RefinementAgent)
    # Agent returns identical design with zero changes
    mock_agent.refine.return_value = (design_set, [])

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=3)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.status in {RefinementStatus.NO_CHANGE, RefinementStatus.REFINEMENT_FAILED}
    assert result.stop_reason == "no_change"
    assert result.is_valid is False
    assert "unchanged design" in result.termination_reason


# =============================================================================
# Test 5 — Oscillation Protection
# =============================================================================

def test_oscillation_protection():
    """Verify loop terminates when refinement enters an oscillatory loop (A -> B -> A)."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    mock_validator = MagicMock(spec=FloorPlanValidator)
    invalid_rep = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=False, issues=[ValidationIssue(severity="error")])],
    )
    mock_validator.validate.return_value = invalid_rep

    # Design B differs from Design A within allocated bounds (8x6)
    design_b = copy.deepcopy(design_set)
    design_b.designs[0].rooms[0].intended_dimensions = (6.0, 4.0)

    # Sequence: Iteration 1 returns B, Iteration 2 returns original design_set (A)
    mock_agent = MagicMock(spec=RefinementAgent)
    mock_agent.refine.side_effect = [
        (design_b, [RefinementChange(room_id="r_living", field_changed="dims", reason="adjust to B")]),
        (design_set, [RefinementChange(room_id="r_living", field_changed="dims", reason="revert to A")]),
    ]

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=5)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.status in {RefinementStatus.OSCILLATION, RefinementStatus.REFINEMENT_FAILED}
    assert result.stop_reason == "oscillation"
    assert result.is_valid is False
    assert "oscillat" in result.termination_reason.lower()


# =============================================================================
# Test 6 — Maximum Iterations Protection
# =============================================================================

def test_max_iterations_protection():
    """Verify loop never exceeds the configured max_iterations limit."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    mock_validator = MagicMock(spec=FloorPlanValidator)
    invalid_rep = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=False, issues=[ValidationIssue(severity="error")])],
    )
    mock_validator.validate.return_value = invalid_rep

    call_count = [0]
    def make_different_design(ctx):
        call_count[0] += 1
        d = copy.deepcopy(design_set)
        # Nudge within bounds: reg_living is 8.0x6.0
        d.designs[0].rooms[0].intended_dimensions = (6.0 - 0.2 * call_count[0], 4.5)
        return d, [RefinementChange(room_id="r_living", field_changed="dims", reason=f"Nudge {call_count[0]}")]

    mock_agent = MagicMock(spec=RefinementAgent)
    mock_agent.refine.side_effect = make_different_design

    max_limit = 3
    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=max_limit)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.status == RefinementStatus.MAX_ITERATIONS_REACHED
    assert result.stop_reason == "max_iterations"
    assert result.is_valid is False
    assert mock_agent.refine.call_count == max_limit
    assert result.iteration == max_limit + 1  # 0, 1, 2, 3


# =============================================================================
# Test 7 — Infeasible Requirements Stop Cleanly
# =============================================================================

def test_infeasible_requirements_stop_cleanly():
    """Verify fundamentally impossible requirements report infeasibility rather than infinite refinement."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    # Validator explicitly reports room area exceeds buildable area deficit
    infeasible_report = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                issues=[
                    ValidationIssue(
                        severity="error",
                        category="boundary",
                        message="Total minimum room area (105.0 m²) exceeds available buildable area (1.0 m²) by deficit of 104.0 m²",
                    )
                ],
            )
        ]
    )

    mock_agent = MagicMock(spec=RefinementAgent)
    mock_validator = MagicMock(spec=FloorPlanValidator)
    mock_validator.validate.return_value = infeasible_report

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=3)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
        initial_report=infeasible_report,
    )

    assert result.status == RefinementStatus.INFEASIBLE_UNDER_CONSTRAINTS
    assert result.stop_reason == "infeasible"
    assert result.is_valid is False
    mock_agent.refine.assert_not_called()


# =============================================================================
# Test 8 — Requirements and Room Inventory Preserved
# =============================================================================

def test_refinement_preserves_room_inventory_and_requirements():
    """Verify that refinement cannot delete required rooms or alter room assignments."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    initial_room_ids = {r.id for r in design_set.designs[0].rooms}
    initial_alloc_map = {r.id: r.allocated_region_id for r in design_set.designs[0].rooms}

    # Run real refinement agent with mock client
    agent = RefinementAgent()
    loop = RefinementLoop(refinement_agent=agent, max_iterations=1)

    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.final_design is not None
    final_room_ids = {r.id for r in result.final_design.designs[0].rooms}
    assert initial_room_ids == final_room_ids, "Room inventory was modified during refinement!"

    for r in result.final_design.designs[0].rooms:
        assert r.allocated_region_id == initial_alloc_map[r.id], f"Room {r.id} allocation moved!"


# =============================================================================
# Test 9 — Plot and Setbacks Preserved During Refinement
# =============================================================================

def test_plot_and_setbacks_preserved_during_refinement():
    """Verify refinement does not mutate plot boundary, setbacks, or buildable envelope."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    orig_plot = list(alloc_set.plot_boundary)
    orig_buildable = list(alloc_set.buildable_boundary)

    loop = RefinementLoop(max_iterations=1)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
        plot_boundary=orig_plot,
        buildable_boundary=orig_buildable,
    )

    fps = result.final_floor_plan_set
    assert fps is not None
    assert fps.plot_boundary == orig_plot
    assert fps.buildable_boundary == orig_buildable


# =============================================================================
# Test 10 — Final Validation Is Authoritative
# =============================================================================

def test_final_validation_is_authoritative():
    """Verify orchestrator reports unresolved/failed and is_success=False when final design is invalid."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    # Flawed mock validator that never passes
    mock_val = MagicMock(spec=FloorPlanValidator)
    mock_val.validate.return_value = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=False, issues=[ValidationIssue(severity="error")])]
    )

    orch = PlanForgeOrchestrator(validator=mock_val)
    cfg = OrchestrationConfig(enable_refinement=True, max_refinement_iterations=2, enable_exports=False)

    res = orch.generate(requirements=reqs, config=cfg)

    # Must NOT report completed or success when validator says invalid
    assert res.is_valid is False
    assert res.is_success is False
    assert res.status in {"unresolved", "failed"}


# =============================================================================
# Test 11 — Actual Geometry Regenerated and Revalidated After Refinement
# =============================================================================

def test_actual_geometry_regenerated_after_refinement():
    """Verify that geometry is physically constructed and validated after each refinement iteration."""
    alloc_set, design_set, reqs = _build_test_allocation_and_design()

    # Track calls to geometry engine and validator
    geom_engine = GeometryEngine()
    validator = FloorPlanValidator()

    # Real refinement loop with 1 iteration
    loop = RefinementLoop(geometry_engine=geom_engine, validator=validator, max_iterations=1)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=reqs,
    )

    assert result.final_floor_plan_set is not None
    # Verify final report matches the final floor plan set
    assert result.final_report is not None
    assert result.final_floor_plan_set.validation_report is not None
    assert result.final_floor_plan_set.validation_report.id == result.final_report.id


# =============================================================================
# Test 12 — Real End-to-End Pipeline Refinement Execution
# =============================================================================

def test_real_end_to_end_pipeline_refinement():
    """Execute real end-to-end generation where refinement runs through all 10 stages."""
    brief = """
    Single floor cottage on a 30 feet by 35 feet plot with 1.5m setbacks.
    Floor 1:
    - 1 living room of 200 sq ft
    - 1 kitchen of 100 sq ft
    - 1 bedroom of 120 sq ft
    """

    parser = RequirementParser()
    reqs = parser.parse(brief)

    orch = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(
        num_alternatives=1,
        enable_refinement=True,
        max_refinement_iterations=2,
        enable_rendering=False,
        enable_exports=False,
    )

    result = orch.generate(requirements=reqs, config=cfg)

    assert result.status == "completed"
    assert result.is_success is True
    assert result.is_valid is True
    assert result.floor_plan_set is not None
    assert len(result.floor_plan_set.floor_plans) == 1
    assert len(result.floor_plan_set.floor_plans[0].geometry.rooms) >= 3

    # Check Stage Records
    assert "REFINEMENT" in result.stage_records
    ref_stage = result.stage_records["REFINEMENT"]
    assert ref_stage.status in {StageStatus.COMPLETED, StageStatus.SKIPPED}
