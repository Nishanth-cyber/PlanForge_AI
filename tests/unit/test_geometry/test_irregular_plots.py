"""Unit tests for irregular and L-shaped plots, boundary containment, and no bounding-box replacement."""

import pytest
from app.geometry.engine import GeometryEngine
from app.geometry.exceptions import RoomOutOfBoundsError
from app.geometry.geometry_utils import is_contained_in, polygon_area
from app.geometry.polygon_builder import PolygonBuilder
from app.geometry.room_builder import RoomBuilder
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)


def test_irregular_l_shaped_plot_preservation():
    """Verify irregular polygonal plot boundary is preserved without bounding-box replacement."""
    # 6-vertex L-shaped plot
    l_plot = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 10.0),
        (10.0, 10.0),
        (10.0, 20.0),
        (0.0, 20.0),
    ]

    # Setback boundary: inset by 1.5m
    l_buildable = [
        (1.5, 1.5),
        (18.5, 1.5),
        (18.5, 8.5),
        (8.5, 8.5),
        (8.5, 18.5),
        (1.5, 18.5),
    ]

    reg_living = AllocatedRegion(
        id="reg_l1",
        room_type="living",
        polygon=[(1.5, 1.5), (8.5, 1.5), (8.5, 8.5), (1.5, 8.5)],
    )

    room_living = RoomDesign(
        id="des_l1",
        room_type="living",
        allocated_region_id="reg_l1",
        intended_shape="rectangular",
    )

    design_set = ArchitecturalDesignSet(designs=[ArchitecturalDesign(floor_number=1, rooms=[room_living])])
    alloc_set = AllocationSet(allocations=[Allocation(floor_number=1, allocated_regions=[reg_living])])

    engine = GeometryEngine()
    fps = engine.construct(
        design_set=design_set,
        allocation_set=alloc_set,
        plot_boundary=l_plot,
        buildable_boundary=l_buildable,
    )

    assert fps.plot_boundary == l_plot
    assert len(fps.plot_boundary) == 6  # Strictly not a 4-vertex bounding box
    assert fps.buildable_boundary == l_buildable
    assert len(fps.buildable_boundary) == 6

    fp1 = fps.get_floor_plan(1)
    geom = fp1.geometry
    assert geom.plot_polygon == l_plot
    assert geom.buildable_polygon == l_buildable

    # Verify room is strictly inside buildable boundary
    living_room = geom.rooms[0]
    assert is_contained_in(living_room.built_polygon, l_buildable)


def test_room_construction_inside_l_shaped_allocated_region():
    """Verify room builder handles L-shaped allocated region cleanly."""
    l_region_coords = [
        (0.0, 0.0),
        (8.0, 0.0),
        (8.0, 4.0),
        (4.0, 4.0),
        (4.0, 8.0),
        (0.0, 8.0),
    ]
    alloc_reg = AllocatedRegion(
        id="reg_l_room",
        room_type="living",
        polygon=l_region_coords,
    )

    room_design = RoomDesign(
        id="des_l_room",
        room_type="living",
        allocated_region_id="reg_l_room",
        intended_shape="l_shaped",
    )

    geo_room = RoomBuilder.build_room(room_design, alloc_reg)
    assert len(geo_room.built_polygon) == 6
    assert is_contained_in(geo_room.built_polygon, l_region_coords)
    assert is_contained_in(geo_room.usable_polygon, geo_room.built_polygon)
    assert geo_room.area_sqm > 0
