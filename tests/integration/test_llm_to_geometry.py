"""Integration test for LLM Architectural Design to Geometry Engine conversion."""

from app.geometry.engine import GeometryEngine
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.floor_plan import FloorPlanSet
from app.models.windows import WindowIntent


def test_architectural_design_to_geometry_conversion():
    """Verify conversion of multi-room architectural proposal into valid FloorPlanSet."""
    # Build 2-floor allocations
    f1_reg_living = AllocatedRegion(
        id="alloc_f1_liv",
        room_type="living",
        floor_number=1,
        polygon=[(0, 0), (6, 0), (6, 5), (0, 5)],
    )
    f1_reg_kitchen = AllocatedRegion(
        id="alloc_f1_kit",
        room_type="kitchen",
        floor_number=1,
        polygon=[(6, 0), (10, 0), (10, 5), (6, 5)],
    )
    f2_reg_bed = AllocatedRegion(
        id="alloc_f2_bed",
        room_type="master_bedroom",
        floor_number=2,
        polygon=[(0, 0), (7, 0), (7, 5), (0, 5)],
    )
    f2_reg_bath = AllocatedRegion(
        id="alloc_f2_bath",
        room_type="bathroom",
        floor_number=2,
        polygon=[(7, 0), (10, 0), (10, 5), (7, 5)],
    )

    alloc_set = AllocationSet(
        allocations=[
            Allocation(floor_number=1, allocated_regions=[f1_reg_living, f1_reg_kitchen]),
            Allocation(floor_number=2, allocated_regions=[f2_reg_bed, f2_reg_bath]),
        ]
    )

    # Architectural Design proposals
    d_liv = RoomDesign(
        id="des_f1_liv",
        room_type="living",
        allocated_region_id="alloc_f1_liv",
        floor_number=1,
        doors=[
            DoorIntent(connects_from="living", connects_to="kitchen", door_type="interior"),
            DoorIntent(connects_from="living", connects_to="exterior", door_type="entrance", wall_orientation="south"),
        ],
        windows=[WindowIntent(room_id="living", wall_orientation="north")],
    )
    d_kit = RoomDesign(
        id="des_f1_kit",
        room_type="kitchen",
        allocated_region_id="alloc_f1_kit",
        floor_number=1,
        windows=[WindowIntent(room_id="kitchen", wall_orientation="east")],
    )

    d_bed = RoomDesign(
        id="des_f2_bed",
        room_type="master_bedroom",
        allocated_region_id="alloc_f2_bed",
        floor_number=2,
        doors=[DoorIntent(connects_from="master_bedroom", connects_to="bathroom", door_type="interior")],
        windows=[WindowIntent(room_id="master_bedroom", wall_orientation="north")],
    )
    d_bath = RoomDesign(
        id="des_f2_bath",
        room_type="bathroom",
        allocated_region_id="alloc_f2_bath",
        floor_number=2,
        windows=[WindowIntent(room_id="bathroom", wall_orientation="east")],
    )

    design_set = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(floor_number=1, rooms=[d_liv, d_kit]),
            ArchitecturalDesign(floor_number=2, rooms=[d_bed, d_bath]),
        ]
    )

    engine = GeometryEngine()
    fps = engine.construct(design_set, alloc_set, project_name="Dual Floor Villa")

    assert isinstance(fps, FloorPlanSet)
    assert len(fps.floor_plans) == 2

    fp1 = fps.get_floor_plan(1)
    fp2 = fps.get_floor_plan(2)

    assert fp1 is not None and fp2 is not None
    assert len(fp1.geometry.rooms) == 2
    assert len(fp2.geometry.rooms) == 2

    # Verify doors exist on both floors
    assert len(fp1.geometry.doors) == 2
    assert len(fp2.geometry.doors) == 1

    # Verify windows exist on both floors
    assert len(fp1.geometry.windows) == 2
    assert len(fp2.geometry.windows) == 2

    # Verify walls exist
    assert len(fp1.geometry.walls) >= 7
    assert len(fp2.geometry.walls) >= 7
