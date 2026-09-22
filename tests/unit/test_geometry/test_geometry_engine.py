"""Unit tests for GeometryEngine: single & multi-floor geometry, determinism, and metadata."""

import pytest
from app.geometry.engine import GeometryEngine
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.floor_plan import FloorPlanSet
from app.models.staircase import StaircaseIntent
from app.models.windows import WindowIntent


def _create_sample_design_and_allocation():
    """Helper to build a coordinated 2-room + staircase floor setup."""
    # ASAA Allocation
    r1_reg = AllocatedRegion(
        id="alloc_living",
        room_type="living",
        floor_number=1,
        polygon=[(0.0, 0.0), (6.0, 0.0), (6.0, 5.0), (0.0, 5.0)],
    )
    r2_reg = AllocatedRegion(
        id="alloc_dining",
        room_type="dining",
        floor_number=1,
        polygon=[(6.0, 0.0), (10.0, 0.0), (10.0, 5.0), (6.0, 5.0)],
    )
    stair_reg = AllocatedRegion(
        id="alloc_stair",
        room_type="staircase",
        zone_type="staircase",
        floor_number=1,
        polygon=[(0.0, 5.0), (3.0, 5.0), (3.0, 8.0), (0.0, 8.0)],
    )

    allocation = Allocation(
        id="alloc_f1",
        floor_number=1,
        allocated_regions=[r1_reg, r2_reg, stair_reg],
    )
    alloc_set = AllocationSet(
        id="alloc_set_1",
        allocations=[allocation],
    )

    # Architectural Design
    d_living = RoomDesign(
        id="des_living",
        room_type="living",
        allocated_region_id="alloc_living",
        floor_number=1,
        intended_shape="rectangular",
        doors=[
            DoorIntent(
                id="d_ent",
                connects_from="living",
                connects_to="exterior",
                door_type="entrance",
                wall_orientation="south",
            ),
            DoorIntent(
                id="d_liv_din",
                connects_from="living",
                connects_to="dining",
                door_type="interior",
            ),
        ],
        windows=[
            WindowIntent(
                id="w_liv",
                room_id="living",
                wall_orientation="west",
            )
        ],
    )

    d_dining = RoomDesign(
        id="des_dining",
        room_type="dining",
        allocated_region_id="alloc_dining",
        floor_number=1,
        intended_shape="rectangular",
        windows=[
            WindowIntent(
                id="w_din",
                room_id="dining",
                wall_orientation="east",
            )
        ],
    )

    stair_intent = StaircaseIntent(
        id="stair_intent_1",
        from_floor=1,
        to_floor=2,
        allocated_region_id="alloc_stair",
    )

    arch_design = ArchitecturalDesign(
        id="arch_f1",
        floor_number=1,
        rooms=[d_living, d_dining],
        staircase_intent=stair_intent,
        allocation_id="alloc_f1",
    )
    design_set = ArchitecturalDesignSet(
        id="arch_set_1",
        designs=[arch_design],
        allocation_set_id="alloc_set_1",
    )

    return design_set, alloc_set


def test_geometry_engine_construct_floor_plan_set():
    """Verify complete construction into FloorPlanSet."""
    design_set, alloc_set = _create_sample_design_and_allocation()
    engine = GeometryEngine()

    plot_boundary = [(0.0, 0.0), (12.0, 0.0), (12.0, 10.0), (0.0, 10.0)]
    buildable_boundary = [(1.0, 1.0), (11.0, 1.0), (11.0, 9.0), (1.0, 9.0)]

    floor_plan_set = engine.construct(
        design_set=design_set,
        allocation_set=alloc_set,
        plot_boundary=plot_boundary,
        buildable_boundary=buildable_boundary,
        project_name="Test Residence",
    )

    assert isinstance(floor_plan_set, FloorPlanSet)
    assert len(floor_plan_set.floor_plans) == 1

    fp1 = floor_plan_set.get_floor_plan(1)
    assert fp1 is not None
    assert fp1.floor_number == 1
    assert fp1.is_valid is False  # Phase 7 responsibility
    assert fp1.validation is None

    geom = fp1.geometry
    assert geom is not None
    assert len(geom.rooms) == 2  # living + dining
    assert len(geom.walls) >= 7  # exterior + shared interior walls
    assert len(geom.doors) == 2  # entrance + shared interior door
    assert len(geom.windows) == 2  # living window + dining window
    assert len(geom.staircases) == 1

    # Check traceability
    room_types = {r.room_type for r in geom.rooms}
    assert "living" in room_types
    assert "dining" in room_types

    # Usable area check
    assert fp1.usable_area() > 0


def test_geometry_engine_determinism():
    """Verify that identical inputs produce bitwise-identical geometry coordinates."""
    design_set, alloc_set = _create_sample_design_and_allocation()
    engine = GeometryEngine()

    fps1 = engine.construct(design_set, alloc_set)
    fps2 = engine.construct(design_set, alloc_set)

    geom1 = fps1.floor_plans[0].geometry
    geom2 = fps2.floor_plans[0].geometry

    # Compare room polygons
    assert len(geom1.rooms) == len(geom2.rooms)
    for r1, r2 in zip(geom1.rooms, geom2.rooms):
        assert r1.room_type == r2.room_type
        assert r1.built_polygon == r2.built_polygon
        assert r1.usable_polygon == r2.usable_polygon
        assert r1.area_sqm == r2.area_sqm

    # Compare wall coordinates
    assert len(geom1.walls) == len(geom2.walls)
    for w1, w2 in zip(geom1.walls, geom2.walls):
        assert w1.start == w2.start
        assert w1.end == w2.end
        assert w1.type == w2.type

    # Compare door positions
    assert len(geom1.doors) == len(geom2.doors)
    for d1, d2 in zip(geom1.doors, geom2.doors):
        assert d1.position == d2.position
        assert d1.swing_arc == d2.swing_arc


def test_geometry_engine_non_adjacent_door_fallback():
    """Verify that a door intent between non-adjacent rooms automatically falls back to circulation without crashing."""
    r1_reg = AllocatedRegion(
        id="alloc_dining",
        room_type="dining",
        floor_number=1,
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
    )
    r2_reg = AllocatedRegion(
        id="alloc_kitchen",
        room_type="kitchen",
        floor_number=1,
        polygon=[(10.0, 0.0), (14.0, 0.0), (14.0, 4.0), (10.0, 4.0)],
    )

    allocation = Allocation(
        id="alloc_f1",
        floor_number=1,
        allocated_regions=[r1_reg, r2_reg],
    )
    alloc_set = AllocationSet(id="alloc_set_fallback", allocations=[allocation])

    # Design intent specifies a direct door between non-adjacent dining and kitchen
    d_dining = RoomDesign(
        id="des_dining",
        room_type="dining",
        allocated_region_id="alloc_dining",
        floor_number=1,
        intended_shape="rectangular",
        doors=[
            DoorIntent(
                id="door_non_adj",
                connects_from="dining",
                connects_to="kitchen",
                door_type="interior",
            )
        ],
    )
    d_kitchen = RoomDesign(
        id="des_kitchen",
        room_type="kitchen",
        allocated_region_id="alloc_kitchen",
        floor_number=1,
        intended_shape="rectangular",
    )

    arch_design = ArchitecturalDesign(
        id="arch_f1",
        floor_number=1,
        rooms=[d_dining, d_kitchen],
        allocation_id="alloc_f1",
    )
    design_set = ArchitecturalDesignSet(
        id="design_set_fallback",
        designs=[arch_design],
        allocation_set_id="alloc_set_fallback",
    )

    engine = GeometryEngine()
    # Must succeed and not raise DoorPlacementError
    fps = engine.construct(design_set, alloc_set)
    assert len(fps.floor_plans) == 1
    geom = fps.floor_plans[0].geometry

    # 1. Verify no extra rooms or corridors were invented
    assert len(geom.rooms) == 2
    assert {r.room_type for r in geom.rooms} == {"dining", "kitchen"}

    # 2. Verify room geometry was not altered
    dining_geo = next(r for r in geom.rooms if r.room_type == "dining")
    assert dining_geo.built_polygon == [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    assert dining_geo.usable_polygon == [(0.1, 0.1), (0.1, 3.9), (3.9, 3.9), (3.9, 0.1)]
    assert dining_geo.area_sqm == 14.44

    # 3. Verify door fallback semantics: connects to circulation, not directly to non-adjacent kitchen
    assert len(geom.doors) == 1
    placed_door = geom.doors[0]
    assert placed_door.connects_from == "dining"
    assert placed_door.connects_to == "circulation"
    assert placed_door.intent_id == "door_non_adj"

    # 4. Verify upstream DoorIntent was not mutated in place
    assert d_dining.doors[0].connects_to == "kitchen"

