"""Unit tests for WallBuilder: exterior walls, interior partitions, thickness, and deduplication."""

import pytest
from app.geometry.wall_builder import WallBuilder
from app.models.geometry import GeoRoom


def test_wall_builder_exterior_and_interior():
    """Verify wall generation for two adjacent rooms sharing a partition wall."""
    # Room 1: (0, 0) to (4, 4)
    r1 = GeoRoom(
        id="room_1",
        room_type="living",
        built_polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        floor_number=1,
    )

    # Room 2: (4, 0) to (8, 4) - shares wall x=4 from y=0 to y=4
    r2 = GeoRoom(
        id="room_2",
        room_type="dining",
        built_polygon=[(4.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0)],
        floor_number=1,
    )

    walls = WallBuilder.build_walls_for_rooms(
        rooms=[r1, r2],
        floor_number=1,
        exterior_thickness=0.20,
        interior_thickness=0.15,
    )

    # Two 4-segment squares sharing 1 wall: total walls = 4 + 4 - 1 = 7 walls
    assert len(walls) == 7

    # Check that exactly 1 interior wall exists
    interior_walls = [w for w in walls if w.type == "interior"]
    exterior_walls = [w for w in walls if w.type == "exterior"]

    assert len(interior_walls) == 1
    assert len(exterior_walls) == 6

    # Verify shared wall has both room IDs
    shared_w = interior_walls[0]
    assert set(shared_w.room_ids) == {"room_1", "room_2"}
    assert shared_w.thickness == 0.15

    # Check wall polygon exists and has 4 vertices
    assert len(shared_w.polygon) == 4

    # Verify room associations
    assert shared_w.id in r1.walls
    assert shared_w.id in r2.walls


def test_wall_builder_no_duplicate_shared_walls():
    """Verify no duplicate walls are created for shared boundaries."""
    r1 = GeoRoom(
        id="r1",
        room_type="bed",
        built_polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0)],
    )
    r2 = GeoRoom(
        id="r2",
        room_type="bath",
        built_polygon=[(0.0, 3.0), (3.0, 3.0), (3.0, 5.0), (0.0, 5.0)],
    )

    walls = WallBuilder.build_walls_for_rooms([r1, r2])
    # Total segments: 4 + 4 - 1 shared = 7 walls
    assert len(walls) == 7
    interior_walls = [w for w in walls if w.type == "interior"]
    assert len(interior_walls) == 1
