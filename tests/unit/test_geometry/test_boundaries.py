"""Stage boundary and invariant tests for Phase 6 Geometry Engine.

Verifies:
- Geometry Engine CONSTRUCTS exact geometry without architectural redesign.
- Zero rooms are invented or deleted.
- No rooms move to other floors or other allocations.
- Validation results and scores are NOT computed (strictly Phase 7).
- Refinement loops are NOT triggered (strictly Phase 8).
"""

import pytest
from app.geometry.engine import GeometryEngine
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)


def test_geometry_engine_does_not_invent_or_delete_rooms():
    """Verify exact 1-to-1 preservation of proposed room designs."""
    rooms = [
        RoomDesign(id="r1", room_type="living", allocated_region_id="reg1", floor_number=1),
        RoomDesign(id="r2", room_type="dining", allocated_region_id="reg2", floor_number=1),
        RoomDesign(id="r3", room_type="kitchen", allocated_region_id="reg3", floor_number=1),
    ]
    regions = [
        AllocatedRegion(id="reg1", room_type="living", floor_number=1, polygon=[(0, 0), (4, 0), (4, 4), (0, 4)]),
        AllocatedRegion(id="reg2", room_type="dining", floor_number=1, polygon=[(4, 0), (8, 0), (8, 4), (4, 4)]),
        AllocatedRegion(id="reg3", room_type="kitchen", floor_number=1, polygon=[(8, 0), (12, 0), (12, 4), (8, 4)]),
    ]

    arch_design = ArchitecturalDesign(floor_number=1, rooms=rooms)
    allocation = Allocation(floor_number=1, allocated_regions=regions)

    design_set = ArchitecturalDesignSet(designs=[arch_design])
    alloc_set = AllocationSet(allocations=[allocation])

    engine = GeometryEngine()
    floor_plan_set = engine.construct(design_set, alloc_set)

    fp = floor_plan_set.get_floor_plan(1)
    geom = fp.geometry

    # Non-corridor rooms must match input exactly
    habitable_rooms = [r for r in geom.rooms if not r.is_corridor]
    assert len(habitable_rooms) == 3

    out_types = [r.room_type for r in habitable_rooms]
    assert out_types == ["living", "dining", "kitchen"]

    out_arch_ids = [r.architectural_room_id for r in habitable_rooms]
    assert out_arch_ids == ["r1", "r2", "r3"]


def test_geometry_engine_does_not_perform_validation():
    """Verify FloorPlan validation properties remain uncertified (Phase 7)."""
    room = RoomDesign(id="r_bed", room_type="bedroom", allocated_region_id="reg_b", floor_number=1)
    region = AllocatedRegion(id="reg_b", room_type="bedroom", floor_number=1, polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])

    design_set = ArchitecturalDesignSet(designs=[ArchitecturalDesign(floor_number=1, rooms=[room])])
    alloc_set = AllocationSet(allocations=[Allocation(floor_number=1, allocated_regions=[region])])

    engine = GeometryEngine()
    fps = engine.construct(design_set, alloc_set)

    for fp in fps.floor_plans:
        assert fp.is_valid is False
        assert fp.validation is None
    assert fps.validation_report is None


def test_geometry_engine_does_not_mutate_floors():
    """Verify rooms strictly stay on their assigned floor number."""
    f1_room = RoomDesign(id="f1_r", room_type="living", allocated_region_id="reg1", floor_number=1)
    f2_room = RoomDesign(id="f2_r", room_type="bedroom", allocated_region_id="reg2", floor_number=2)

    f1_reg = AllocatedRegion(id="reg1", room_type="living", floor_number=1, polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])
    f2_reg = AllocatedRegion(id="reg2", room_type="bedroom", floor_number=2, polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])

    design_set = ArchitecturalDesignSet(designs=[
        ArchitecturalDesign(floor_number=1, rooms=[f1_room]),
        ArchitecturalDesign(floor_number=2, rooms=[f2_room]),
    ])
    alloc_set = AllocationSet(allocations=[
        Allocation(floor_number=1, allocated_regions=[f1_reg]),
        Allocation(floor_number=2, allocated_regions=[f2_reg]),
    ])

    engine = GeometryEngine()
    fps = engine.construct(design_set, alloc_set)

    fp1 = fps.get_floor_plan(1)
    fp2 = fps.get_floor_plan(2)

    assert len(fp1.geometry.rooms) == 1
    assert fp1.geometry.rooms[0].architectural_room_id == "f1_r"
    assert fp1.geometry.rooms[0].floor_number == 1

    assert len(fp2.geometry.rooms) == 1
    assert fp2.geometry.rooms[0].architectural_room_id == "f2_r"
    assert fp2.geometry.rooms[0].floor_number == 2
