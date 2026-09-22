"""Unit tests for RoomBuilder: dual polygons, wall offsets, area, containment, and traceability."""

import pytest
from app.geometry.exceptions import RoomOutOfBoundsError
from app.geometry.geometry_utils import polygon_area
from app.geometry.room_builder import RoomBuilder
from app.models.allocation import AllocatedRegion
from app.models.architectural_design import RoomDesign


def test_build_room_rectangular():
    """Verify GeoRoom construction with dual usable/built polygons and area."""
    alloc_reg = AllocatedRegion(
        id="reg_living",
        room_type="living",
        floor_number=1,
        target_area_sqm=20.0,
        polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)],
    )

    room_design = RoomDesign(
        id="des_living",
        room_type="living",
        allocated_region_id="reg_living",
        floor_number=1,
        intended_shape="rectangular",
        intended_dimensions=(4.0, 3.0),
        intended_area_sqm=12.0,
    )

    geo_room = RoomBuilder.build_room(room_design, alloc_reg, wall_thickness=0.20)

    assert geo_room.room_type == "living"
    assert geo_room.architectural_room_id == "des_living"
    assert geo_room.floor_number == 1
    assert geo_room.is_corridor is False
    assert len(geo_room.built_polygon) == 4
    assert len(geo_room.usable_polygon) >= 4

    # Usable area must be strictly smaller than built area due to wall thickness
    built_area = polygon_area(geo_room.built_polygon)
    usable_area = polygon_area(geo_room.usable_polygon)
    assert 0 < usable_area < built_area
    assert geo_room.area_sqm == round(usable_area, 2)


def test_build_room_containment_violation():
    """Verify RoomOutOfBoundsError when proposed boundary violates allocated region."""
    alloc_reg = AllocatedRegion(
        id="reg_small",
        room_type="study",
        floor_number=1,
        polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0)],
    )

    # Proposed boundary extends way outside (0..3, 0..3)
    room_design = RoomDesign(
        id="des_study",
        room_type="study",
        allocated_region_id="reg_small",
        floor_number=1,
        proposed_boundary=[(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0)],
    )

    with pytest.raises(RoomOutOfBoundsError):
        RoomBuilder.build_room(room_design, alloc_reg)


def test_build_room_traceability():
    """Verify all upstream identifiers are preserved in GeoRoom."""
    alloc_reg = AllocatedRegion(
        id="reg_master",
        room_type="master_bedroom",
        floor_number=2,
        polygon=[(2.0, 2.0), (8.0, 2.0), (8.0, 7.0), (2.0, 7.0)],
    )

    room_design = RoomDesign(
        id="des_master_123",
        room_type="master_bedroom",
        allocated_region_id="reg_master",
        floor_number=2,
        intended_shape="rectangular",
    )

    geo_room = RoomBuilder.build_room(room_design, alloc_reg)
    assert geo_room.architectural_room_id == "des_master_123"
    assert geo_room.floor_number == 2
    assert geo_room.room_type == "master_bedroom"
    assert geo_room.id.startswith("georoom_")
