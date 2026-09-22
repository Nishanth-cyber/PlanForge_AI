"""Unit tests for ArchitecturalAgent multi-floor design generation."""

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_architectural_agent_multi_floor():
    """Test 2-floor design preserves floor distribution and links staircase intents."""
    # Floor 1: Living, Kitchen
    f1_rooms = [
        RoomSpec(id="r1_liv", room_type="living", floor_number=1, target_area_sqm=30.0),
        RoomSpec(id="r1_kit", room_type="kitchen", floor_number=1, target_area_sqm=15.0),
    ]
    f1_spec = FloorPlanSpec(
        floor_number=1,
        floor_name="Ground Floor",
        room_specs=f1_rooms,
        staircase_intent={"required": True, "connects_floors": [1, 2]},
    )

    # Floor 2: Master Bedroom, Bathroom
    f2_rooms = [
        RoomSpec(id="r2_mbr", room_type="master_bedroom", floor_number=2, target_area_sqm=25.0),
        RoomSpec(id="r2_bth", room_type="bathroom", floor_number=2, target_area_sqm=6.0),
    ]
    f2_spec = FloorPlanSpec(
        floor_number=2,
        floor_name="First Floor",
        room_specs=f2_rooms,
        staircase_intent={"required": True, "connects_floors": [1, 2]},
    )

    p_spec = PlanningSpec(floors=[f1_spec, f2_spec])

    # Allocations
    reg_liv = AllocatedRegion(id="reg_liv", room_type="living", room_spec_id="r1_liv", floor_number=1, area_sqm=30.0)
    reg_kit = AllocatedRegion(id="reg_kit", room_type="kitchen", room_spec_id="r1_kit", floor_number=1, area_sqm=15.0)
    reg_stair_1 = AllocatedRegion(id="reg_stair_1", room_type="staircase", zone_type="staircase", floor_number=1, area_sqm=8.0)
    alloc_1 = Allocation(floor_number=1, allocated_regions=[reg_liv, reg_kit, reg_stair_1])

    reg_mbr = AllocatedRegion(id="reg_mbr", room_type="master_bedroom", room_spec_id="r2_mbr", floor_number=2, area_sqm=25.0)
    reg_bth = AllocatedRegion(id="reg_bth", room_type="bathroom", room_spec_id="r2_bth", floor_number=2, area_sqm=6.0)
    reg_stair_2 = AllocatedRegion(id="reg_stair_2", room_type="staircase", zone_type="staircase", floor_number=2, area_sqm=8.0)
    alloc_2 = Allocation(floor_number=2, allocated_regions=[reg_mbr, reg_bth, reg_stair_2])

    alloc_set = AllocationSet(allocations=[alloc_1, alloc_2], staircase_aligned=True)

    agent = ArchitecturalAgent()
    design_set = agent.design(p_spec, alloc_set)

    assert isinstance(design_set, ArchitecturalDesignSet)
    assert len(design_set.designs) == 2

    d1 = design_set.get_design(1)
    d2 = design_set.get_design(2)
    assert d1 is not None
    assert d2 is not None

    # Verify Floor 1 rooms
    d1_types = {r.room_type for r in d1.rooms}
    assert d1_types == {"living", "kitchen"}
    assert d1.staircase_intent is not None
    assert d1.staircase_intent.from_floor == 1
    assert d1.staircase_intent.to_floor == 2

    # Verify Floor 2 rooms
    d2_types = {r.room_type for r in d2.rooms}
    assert d2_types == {"master_bedroom", "bathroom"}
    assert d2.staircase_intent is not None

    # Strict floor preservation
    assert "master_bedroom" not in d1_types
    assert "living" not in d2_types
