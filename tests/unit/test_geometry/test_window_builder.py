"""Unit tests for WindowBuilder: exterior placement, orientation matching, and error handling."""

import pytest
from app.geometry.exceptions import WindowPlacementError
from app.geometry.wall_builder import WallBuilder
from app.geometry.window_builder import WindowBuilder
from app.models.geometry import GeoRoom
from app.models.windows import WindowIntent


def test_build_window_on_north_wall():
    """Verify window placed on north exterior wall."""
    room = GeoRoom(
        id="bedroom_1",
        room_type="bedroom",
        built_polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        floor_number=1,
    )

    walls = WallBuilder.build_walls_for_rooms([room], floor_number=1)

    win_intent = WindowIntent(
        id="intent_win_1",
        room_id="bedroom",
        wall_orientation="north",
        window_type="standard",
        recommended_width=1.2,
        recommended_height=1.5,
        sill_height=0.9,
        floor_number=1,
    )

    geo_win = WindowBuilder.build_window(win_intent, walls, [room], floor_number=1)

    assert geo_win.id.startswith("geowindow_")
    assert geo_win.width == 1.2
    assert geo_win.height == 1.5
    assert geo_win.sill_height == 0.9
    assert geo_win.type == "standard"

    # Must be on an exterior wall
    wall = next(w for w in walls if w.id == geo_win.wall_id)
    assert wall.type == "exterior"

    # Window ID populated in room
    assert geo_win.id in room.windows


def test_window_no_matching_exterior_orientation():
    """Verify WindowPlacementError when room has no exterior wall on requested orientation."""
    # Room completely surrounded: simulated by having only south and east exterior walls
    room = GeoRoom(
        id="inner_room",
        room_type="study",
        built_polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0)],
    )
    walls = WallBuilder.build_walls_for_rooms([room])
    # Force walls to interior except one south wall
    for w in walls:
        w.type = "interior"

    win_intent = WindowIntent(
        id="intent_win_bad",
        room_id="study",
        wall_orientation="north",
    )

    with pytest.raises(WindowPlacementError):
        WindowBuilder.build_window(win_intent, walls, [room])
