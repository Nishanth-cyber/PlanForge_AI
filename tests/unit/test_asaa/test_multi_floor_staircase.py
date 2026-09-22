"""Unit tests for ASAA multi-floor allocation and staircase vertical alignment."""

from app.asaa.allocator import ASAAAllocator
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_two_floor_allocation_with_staircase_alignment():
    """Test 2-floor allocation preserves floor assignments and aligns staircase zones exactly."""
    allocator = ASAAAllocator(seed=42)

    # Floor 1: Living, Dining, Kitchen
    f1_rooms = [
        RoomSpec(room_type="living", floor_number=1, target_area_sqm=30.0),
        RoomSpec(room_type="kitchen", floor_number=1, target_area_sqm=15.0),
        RoomSpec(room_type="dining", floor_number=1, target_area_sqm=15.0),
    ]
    f1_spec = FloorPlanSpec(
        floor_number=1,
        floor_name="Ground Floor",
        room_specs=f1_rooms,
        staircase_intent={"required": True, "connects_floors": [1, 2]},
    )

    # Floor 2: Master Bedroom, Bedroom 2, Bathroom
    f2_rooms = [
        RoomSpec(room_type="master_bedroom", floor_number=2, target_area_sqm=25.0),
        RoomSpec(room_type="bedroom", floor_number=2, target_area_sqm=18.0),
        RoomSpec(room_type="bathroom", floor_number=2, target_area_sqm=8.0),
    ]
    f2_spec = FloorPlanSpec(
        floor_number=2,
        floor_name="First Floor",
        room_specs=f2_rooms,
        staircase_intent={"required": True, "connects_floors": [1, 2]},
    )

    planning_spec = PlanningSpec(
        floors=[f1_spec, f2_spec],
        global_constraints={"plot_width_m": 12.0, "plot_depth_m": 15.0},
    )

    allocation_set = allocator.allocate(planning_spec)

    assert len(allocation_set.allocations) == 2
    assert allocation_set.staircase_aligned is True

    alloc_1 = allocation_set.get_allocation(1)
    alloc_2 = allocation_set.get_allocation(2)
    assert alloc_1 is not None
    assert alloc_2 is not None

    # Verify staircase zone exists on both floors
    stair_1 = alloc_1.get_staircase_region()
    stair_2 = alloc_2.get_staircase_region()
    assert stair_1 is not None
    assert stair_2 is not None

    # Staircase zone coordinates must match between floors
    assert stair_1.polygon == stair_2.polygon
    assert stair_1.centroid == stair_2.centroid

    # Floor assignment preservation
    f1_types = {r.room_type for r in alloc_1.allocated_regions if r.zone_type == "room"}
    f2_types = {r.room_type for r in alloc_2.allocated_regions if r.zone_type == "room"}
    assert "living" in f1_types
    assert "kitchen" in f1_types
    assert "dining" in f1_types
    assert "master_bedroom" in f2_types
    assert "bedroom" in f2_types
    assert "bathroom" in f2_types

    # Ensure no rooms moved across floors
    assert "master_bedroom" not in f1_types
    assert "living" not in f2_types


def test_three_floor_allocation():
    """Test 3-floor building allocation with aligned vertical core."""
    allocator = ASAAAllocator(seed=42)

    floors = []
    for f in range(1, 4):
        rs = [RoomSpec(room_type=f"room_floor_{f}", floor_number=f, target_area_sqm=30.0)]
        floors.append(
            FloorPlanSpec(
                floor_number=f,
                room_specs=rs,
                staircase_intent={"required": True, "connects_floors": [1, 2, 3]},
            )
        )

    spec = PlanningSpec(
        floors=floors,
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 12.0},
    )
    alloc_set = allocator.allocate(spec)

    assert len(alloc_set.allocations) == 3
    assert alloc_set.staircase_aligned is True
    # Verify all 3 floors have identical staircase polygon
    p1 = alloc_set.get_allocation(1).get_staircase_region().polygon
    p2 = alloc_set.get_allocation(2).get_staircase_region().polygon
    p3 = alloc_set.get_allocation(3).get_staircase_region().polygon
    assert p1 == p2 == p3


def test_no_invented_rooms_on_floor_2():
    """Test that ASAA does not synthesize extra rooms on Floor 2."""
    allocator = ASAAAllocator(seed=42)

    f1 = FloorPlanSpec(
        floor_number=1,
        room_specs=[RoomSpec(room_type="living", floor_number=1, target_area_sqm=30.0)],
    )
    f2 = FloorPlanSpec(
        floor_number=2,
        room_specs=[RoomSpec(room_type="studio", floor_number=2, target_area_sqm=25.0)],
    )
    spec = PlanningSpec(
        floors=[f1, f2],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 10.0},
    )
    alloc_set = allocator.allocate(spec)

    alloc_2 = alloc_set.get_allocation(2)
    room_regions = [r for r in alloc_2.allocated_regions if r.zone_type == "room"]
    assert len(room_regions) == 1
    assert room_regions[0].room_type == "studio"
