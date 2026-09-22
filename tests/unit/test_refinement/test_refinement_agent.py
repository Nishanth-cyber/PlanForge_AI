"""Unit tests for RefinementAgent."""

from app.agents.refinement_agent.agent import RefinementAgent
from app.agents.refinement_agent.context import RefinementContextBuilder
from app.models.allocation import Allocation, AllocationSet, AllocatedRegion
from app.models.architectural_design import ArchitecturalDesign, ArchitecturalDesignSet, RoomDesign
from app.models.doors import DoorIntent
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult


def test_refinement_agent_fixes_door_issue():
    """Verify RefinementAgent with deterministic mock fixes a missing entrance door."""
    # Floor design with living room having no entrance door
    floor_design = ArchitecturalDesign(
        floor_number=1,
        rooms=[
            RoomDesign(
                id="r_liv",
                room_type="living",
                allocated_region_id="reg_liv",
                intended_dimensions=(4.0, 5.0),
                doors=[],
            )
        ],
    )
    alloc_set = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="reg_liv",
                        room_type="living",
                        approximate_dimensions=(4.5, 5.5),
                    )
                ],
            )
        ]
    )

    # Validation reported missing entrance connection
    val_res = ValidationResult(floor_number=1, is_valid=False)
    val_res.add_issue(
        ValidationIssue(
            severity="error",
            category="connectivity",
            check="missing_entrance_connection",
            message="Floor 1 has no entrance door",
            room_id="r_liv",
        )
    )
    report = ValidationReport(results=[val_res])

    ctx = RefinementContextBuilder.build(
        requirements=Requirements(),
        planning_spec=PlanningSpec(),
        allocation_set=alloc_set,
        current_design=ArchitecturalDesignSet(designs=[floor_design], version=0),
        validation_report=report,
        iteration=1,
    )

    agent = RefinementAgent()
    revised_set, changes = agent.refine(ctx)

    assert revised_set.version == 1
    assert len(revised_set.designs) == 1
    revised_liv = revised_set.designs[0].rooms[0]
    assert len(revised_liv.doors) > 0
    assert any(d.door_type == "entrance" for d in revised_liv.doors)
    assert len(changes) > 0
    assert any(c.field_changed == "doors" for c in changes)


def test_refinement_agent_preserves_valid_floors():
    """Verify RefinementAgent leaves floors with 0 issues untouched."""
    f1 = ArchitecturalDesign(
        floor_number=1,
        rooms=[RoomDesign(id="r_1", room_type="living", allocated_region_id="reg_1", intended_dimensions=(4.0, 4.0))],
    )
    f2 = ArchitecturalDesign(
        floor_number=2,
        rooms=[RoomDesign(id="r_2", room_type="bedroom", allocated_region_id="reg_2", intended_dimensions=(3.5, 3.5))],
    )
    alloc_set = AllocationSet(
        allocations=[
            Allocation(floor_number=1, allocated_regions=[AllocatedRegion(id="reg_1", room_type="living", approximate_dimensions=(5, 5))]),
            Allocation(floor_number=2, allocated_regions=[AllocatedRegion(id="reg_2", room_type="bedroom", approximate_dimensions=(5, 5))]),
        ]
    )

    # Only Floor 1 has an issue; Floor 2 is valid
    res1 = ValidationResult(floor_number=1, is_valid=False)
    res1.add_issue(ValidationIssue(severity="error", category="door", check="isolated_room", room_id="r_1"))
    res2 = ValidationResult(floor_number=2, is_valid=True)
    report = ValidationReport(results=[res1, res2])

    ctx = RefinementContextBuilder.build(
        requirements=Requirements(),
        planning_spec=PlanningSpec(),
        allocation_set=alloc_set,
        current_design=ArchitecturalDesignSet(designs=[f1, f2], version=0),
        validation_report=report,
        iteration=1,
    )

    agent = RefinementAgent()
    revised_set, changes = agent.refine(ctx)

    # Floor 2 rooms should be preserved unchanged
    revised_f2 = revised_set.get_design(2)
    assert revised_f2 is not None
    assert revised_f2.rooms[0].intended_dimensions == (3.5, 3.5)
    # Only changes for Floor 1 should be recorded
    assert all(c.room_id == "r_1" for c in changes)
