"""Unit tests verifying strict stage boundaries for ASAA.

Verifies that ASAA answers WHERE without generating HOW:
- Does NOT generate doors, door swings, or door intent.
- Does NOT generate windows or window intent.
- Does NOT generate walls or wall thickness.
- Does NOT generate detailed architectural CAD geometry.
"""

from app.asaa.allocator import ASAAAllocator
from app.models.allocation import AllocatedRegion, AllocationSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_asaa_does_not_create_doors_windows_walls():
    """Verify that ASAA output contract contains only spatial regions, never walls, doors, or windows."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=30.0),
                    RoomSpec(room_type="kitchen", target_area_sqm=15.0),
                    RoomSpec(room_type="bedroom", target_area_sqm=20.0),
                ],
            )
        ],
        global_constraints={"plot_width_m": 12.0, "plot_depth_m": 15.0},
    )

    allocator = ASAAAllocator()
    allocation_set = allocator.allocate(spec)

    assert isinstance(allocation_set, AllocationSet)
    alloc = allocation_set.get_allocation(1)

    # Must contain only AllocatedRegion objects
    for r in alloc.allocated_regions:
        assert isinstance(r, AllocatedRegion)
        # Check that no architectural geometry fields exist
        assert not hasattr(r, "doors")
        assert not hasattr(r, "windows")
        assert not hasattr(r, "walls")
        assert not hasattr(r, "wall_thickness")
        assert not hasattr(r, "swing_arc")
        assert not hasattr(r, "usable_polygon")
        assert not hasattr(r, "built_polygon")

        # The region representation must be abstract bounding polygon and centroid
        assert isinstance(r.polygon, list)
        assert isinstance(r.centroid, tuple)
        assert r.zone_type in {"room", "circulation", "entrance", "staircase"}
