"""Unit tests for DoorBuilder: interior doors, entrance doors, swing arcs, and error handling."""

import pytest
from app.geometry.door_builder import DoorBuilder
from app.geometry.exceptions import DoorPlacementError
from app.geometry.wall_builder import WallBuilder
from app.models.doors import DoorIntent
from app.models.geometry import GeoRoom


def test_build_interior_door_between_rooms():
    """Verify interior door placed on shared wall with swing arc."""
    r1 = GeoRoom(
        id="living_1",
        room_type="living",
        built_polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        floor_number=1,
    )
    r2 = GeoRoom(
        id="dining_1",
        room_type="dining",
        built_polygon=[(4.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0)],
        floor_number=1,
    )

    walls = WallBuilder.build_walls_for_rooms([r1, r2], floor_number=1)

    door_intent = DoorIntent(
        id="intent_door_1",
        connects_from="living",
        connects_to="dining",
        door_type="interior",
        recommended_width=0.9,
        floor_number=1,
    )

    geo_door = DoorBuilder.build_door(door_intent, walls, [r1, r2], floor_number=1)

    assert geo_door.id.startswith("geodoor_")
    assert geo_door.intent_id == "intent_door_1"
    assert geo_door.width == 0.9
    assert geo_door.height == 2.1
    assert geo_door.type == "interior"
    assert geo_door.swing_arc is not None
    assert len(geo_door.swing_arc) >= 3

    # Wall must be the shared interior wall
    wall = next(w for w in walls if w.id == geo_door.wall_id)
    assert wall.type == "interior"
    assert set(wall.room_ids) == {"living_1", "dining_1"}

    # Door ID populated in both rooms
    assert geo_door.id in r1.doors
    assert geo_door.id in r2.doors


def test_build_entrance_door():
    """Verify entrance door placed on exterior wall."""
    r1 = GeoRoom(
        id="living_1",
        room_type="living",
        built_polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)],
        floor_number=1,
    )

    walls = WallBuilder.build_walls_for_rooms([r1], floor_number=1)

    door_intent = DoorIntent(
        id="intent_entrance",
        connects_from="living",
        connects_to="exterior",
        door_type="entrance",
        wall_orientation="south",
        recommended_width=1.0,
        floor_number=1,
    )

    geo_door = DoorBuilder.build_door(door_intent, walls, [r1], floor_number=1)

    assert geo_door.type == "entrance"
    assert geo_door.width == 1.0

    wall = next(w for w in walls if w.id == geo_door.wall_id)
    assert wall.type == "exterior"


def test_door_placement_impossible_non_adjacent():
    """Verify DoorPlacementError when two rooms are non-adjacent."""
    r1 = GeoRoom(
        id="room_a",
        room_type="kitchen",
        built_polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0)],
    )
    r2 = GeoRoom(
        id="room_b",
        room_type="master_bedroom",
        built_polygon=[(10.0, 10.0), (14.0, 10.0), (14.0, 14.0), (10.0, 14.0)],
    )

    walls = WallBuilder.build_walls_for_rooms([r1, r2])

    door_intent = DoorIntent(
        id="intent_bad_door",
        connects_from="kitchen",
        connects_to="master_bedroom",
        door_type="interior",
    )

    with pytest.raises(DoorPlacementError):
        DoorBuilder.build_door(door_intent, walls, [r1, r2])


def test_build_balcony_door():
    """Verify balcony door placed on room's exterior wall."""
    room = GeoRoom(
        id="master_1",
        room_type="master_bedroom",
        built_polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)],
        floor_number=2,
    )
    walls = WallBuilder.build_walls_for_rooms([room], floor_number=2)

    door_intent = DoorIntent(
        id="intent_balcony",
        connects_from="master_bedroom",
        connects_to="balcony",
        door_type="balcony",
        wall_orientation="north",
        recommended_width=1.0,
        floor_number=2,
    )

    geo_door = DoorBuilder.build_door(door_intent, walls, [room], floor_number=2)
    assert geo_door.type == "balcony"
    assert geo_door.width == 1.0
    wall = next(w for w in walls if w.id == geo_door.wall_id)
    assert wall.type == "exterior"
