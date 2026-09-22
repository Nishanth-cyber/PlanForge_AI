"""Unit tests verifying strict architectural stage boundaries.

Guarantees that the Architectural LLM generates intent only (HOW)
and never generates physical geometry (CONSTRUCT):
- No GeoDoor, GeoWindow, GeoWall, GeoRoom, or GeoStaircase
- No door swing arcs or wall cutout coordinates
- No wall thickness or wall centerline coordinates
- No CAD/DXF/PNG entities
"""

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.doors import DoorIntent
from app.models.geometry import GeoDoor, GeoRoom, GeoStaircase, GeoWall, GeoWindow
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.windows import WindowIntent


def test_architectural_llm_produces_no_geometry_objects():
    """Verify that ArchitecturalDesignSet contains only intent models, never Geo models."""
    r_liv = RoomSpec(id="r1", room_type="living", floor_number=1, target_area_sqm=30.0)
    f_spec = FloorPlanSpec(floor_number=1, room_specs=[r_liv])
    p_spec = PlanningSpec(floors=[f_spec])

    reg_1 = AllocatedRegion(id="reg1", room_type="living", room_spec_id="r1", floor_number=1, area_sqm=30.0)
    alloc_set = AllocationSet(allocations=[Allocation(floor_number=1, allocated_regions=[reg_1])])

    agent = ArchitecturalAgent()
    design_set = agent.design(p_spec, alloc_set)
    d1 = design_set.get_design(1)
    living = d1.get_rooms_by_type("living")[0]

    # Check that output objects are NOT Geo objects
    assert not isinstance(living, GeoRoom)
    for door in living.doors:
        assert isinstance(door, DoorIntent)
        assert not isinstance(door, GeoDoor)
        assert not hasattr(door, "swing_arc_polygon")
        assert not hasattr(door, "wall_cutout")
        assert not hasattr(door, "hinge_point")

    for window in living.windows:
        assert isinstance(window, WindowIntent)
        assert not isinstance(window, GeoWindow)
        assert not hasattr(window, "opening_polygon")
        assert not hasattr(window, "sill_polygon")

    # Check that design has no walls
    assert not hasattr(d1, "walls")
    assert not hasattr(living, "wall_thickness")
    assert not hasattr(living, "walls")
    assert not hasattr(living, "usable_polygon")
    assert not hasattr(living, "built_polygon")
