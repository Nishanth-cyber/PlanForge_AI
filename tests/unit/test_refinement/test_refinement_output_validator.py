"""Unit tests for RefinementOutputValidator."""

import pytest
from app.agents.architectural_agent.structured_output import (
    AllocationMismatchError,
    DimensionExceedsAllocationError,
    MalformedLLMResponseError,
    RoomCoverageError,
)
from app.agents.refinement_agent.output_validator import RefinementOutputValidator
from app.models.allocation import Allocation, AllocatedRegion
from app.models.architectural_design import ArchitecturalDesign, RoomDesign


@pytest.fixture
def current_floor_and_allocation():
    alloc = Allocation(
        floor_number=1,
        allocated_regions=[
            AllocatedRegion(id="reg_1", room_type="living", approximate_dimensions=(5.0, 5.0)),
            AllocatedRegion(id="reg_2", room_type="kitchen", approximate_dimensions=(3.0, 4.0)),
        ],
    )
    design = ArchitecturalDesign(
        floor_number=1,
        rooms=[
            RoomDesign(id="r_1", room_type="living", allocated_region_id="reg_1", intended_dimensions=(4.0, 4.0)),
            RoomDesign(id="r_2", room_type="kitchen", allocated_region_id="reg_2", intended_dimensions=(2.5, 3.5)),
        ],
    )
    return design, alloc


def test_valid_refinement_and_change_extraction(current_floor_and_allocation):
    """Verify valid refinement output is parsed and changes are properly tracked."""
    design, alloc = current_floor_and_allocation

    raw_dict = {
        "rooms": [
            {
                "id": "r_1",
                "room_type": "living",
                "allocated_region_id": "reg_1",
                "intended_shape": "rectangular",
                "intended_dimensions": [4.5, 4.5],  # Changed from (4.0, 4.0)
                "doors": [{"wall_orientation": "south", "connects_to": "exterior", "door_type": "entrance"}],
                "windows": [],
                "design_rationale": "Expanded living room and added entrance door",
            },
            {
                "id": "r_2",
                "room_type": "kitchen",
                "allocated_region_id": "reg_2",
                "intended_shape": "rectangular",
                "intended_dimensions": [2.5, 3.5],  # Unchanged
                "doors": [],
                "windows": [],
                "design_rationale": "Unchanged",
            },
        ],
        "refinement_rationale": "Resolved entrance and sizing issues",
    }

    revised_rooms, changes, rationale = RefinementOutputValidator.validate_and_parse(
        raw_dict=raw_dict,
        current_floor_design=design,
        allocation=alloc,
    )

    assert len(revised_rooms) == 2
    assert rationale == "Resolved entrance and sizing issues"

    # Verify changes recorded for r_1
    r1_changes = [c for c in changes if c.room_id == "r_1"]
    assert any(c.field_changed == "intended_dimensions" for c in r1_changes)
    assert any(c.field_changed == "doors" for c in r1_changes)

    # Verify no changes recorded for r_2
    r2_changes = [c for c in changes if c.room_id == "r_2"]
    assert len(r2_changes) == 0


def test_reject_invented_room(current_floor_and_allocation):
    """Verify invented room IDs are rejected."""
    design, alloc = current_floor_and_allocation
    raw_dict = {
        "rooms": [
            {"id": "r_1", "allocated_region_id": "reg_1"},
            {"id": "r_2", "allocated_region_id": "reg_2"},
            {"id": "r_invented_3", "allocated_region_id": "reg_1"},
        ]
    }
    with pytest.raises(RoomCoverageError, match="invented or unrequested"):
        RefinementOutputValidator.validate_and_parse(raw_dict, design, alloc)


def test_reject_missing_room(current_floor_and_allocation):
    """Verify dropping required rooms is rejected."""
    design, alloc = current_floor_and_allocation
    raw_dict = {
        "rooms": [
            {"id": "r_1", "allocated_region_id": "reg_1"},
            # r_2 is missing
        ]
    }
    with pytest.raises(RoomCoverageError, match="dropped required existing rooms"):
        RefinementOutputValidator.validate_and_parse(raw_dict, design, alloc)


def test_reject_allocation_change(current_floor_and_allocation):
    """Verify moving a room to a different allocation is rejected."""
    design, alloc = current_floor_and_allocation
    raw_dict = {
        "rooms": [
            {"id": "r_1", "allocated_region_id": "reg_2"},  # Changed from reg_1 to reg_2
            {"id": "r_2", "allocated_region_id": "reg_2"},
        ]
    }
    with pytest.raises(AllocationMismatchError, match="immutable during refinement"):
        RefinementOutputValidator.validate_and_parse(raw_dict, design, alloc)


def test_reject_raw_geometry(current_floor_and_allocation):
    """Verify raw CAD geometry keys in LLM output are rejected."""
    design, alloc = current_floor_and_allocation
    raw_dict = {
        "rooms": [
            {"id": "r_1", "polygon": [(0, 0), (4, 0), (4, 4), (0, 4)]},
            {"id": "r_2", "allocated_region_id": "reg_2"},
        ]
    }
    with pytest.raises(MalformedLLMResponseError, match="forbidden raw geometry keys"):
        RefinementOutputValidator.validate_and_parse(raw_dict, design, alloc)


def test_reject_dimension_exceeding_allocation(current_floor_and_allocation):
    """Verify proposing dimensions exceeding allocated bounds is rejected."""
    design, alloc = current_floor_and_allocation
    # reg_1 is 5.0 x 5.0m. Output proposes 12.0 x 12.0m
    raw_dict = {
        "rooms": [
            {"id": "r_1", "allocated_region_id": "reg_1", "intended_dimensions": [12.0, 12.0]},
            {"id": "r_2", "allocated_region_id": "reg_2"},
        ]
    }
    with pytest.raises(DimensionExceedsAllocationError, match="exceed ASAA allocated region bounds"):
        RefinementOutputValidator.validate_and_parse(raw_dict, design, alloc)
