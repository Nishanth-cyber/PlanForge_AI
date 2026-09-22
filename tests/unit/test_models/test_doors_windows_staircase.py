"""Unit tests for Door, Window, and Staircase Intent data contracts."""

from app.models.doors import DoorIntent, DoorSpec
from app.models.windows import WindowIntent, WindowSpec
from app.models.staircase import StaircaseIntent, StaircaseSpec


def test_door_intent_and_spec_alias():
    """Verify DoorIntent fields and DoorSpec alias equivalence."""
    assert DoorSpec is DoorIntent

    door = DoorIntent(
        connects_from="living",
        connects_to="dining",
        wall_orientation="north",
        door_type="interior",
        recommended_width=0.9,
        recommended_height=2.1,
        floor_number=1,
        rationale="Primary social circulation between living and dining",
    )
    assert door.id is not None
    assert door.connects_from == "living"
    assert door.connects_to == "dining"
    assert door.wall_orientation == "north"
    assert door.door_type == "interior"
    assert door.recommended_width == 0.9


def test_window_intent_and_spec_alias():
    """Verify WindowIntent fields and WindowSpec alias equivalence."""
    assert WindowSpec is WindowIntent

    win = WindowIntent(
        room_id="bedroom_01",
        wall_orientation="east",
        window_type="standard",
        recommended_width=1.5,
        recommended_height=1.2,
        sill_height=0.85,
        floor_number=1,
        rationale="Morning natural daylight for bedroom",
    )
    assert win.id is not None
    assert win.room_id == "bedroom_01"
    assert win.wall_orientation == "east"
    assert win.window_type == "standard"
    assert win.sill_height == 0.85


def test_staircase_intent_and_spec_alias():
    """Verify StaircaseIntent fields and StaircaseSpec alias equivalence."""
    assert StaircaseSpec is StaircaseIntent

    stairs = StaircaseIntent(
        from_floor=1,
        to_floor=2,
        stair_type="u_shaped",
        approx_location=(10.0, 5.0),
        allocated_region_id="region_stair_01",
        recommended_width=1.1,
        connects_to_rooms=["hallway_01", "hallway_02"],
        floor_number=1,
        rationale="Central vertical core connecting ground and upper floor",
    )
    assert stairs.id is not None
    assert stairs.from_floor == 1
    assert stairs.to_floor == 2
    assert stairs.stair_type == "u_shaped"
    assert stairs.approx_location == (10.0, 5.0)
    assert "hallway_01" in stairs.connects_to_rooms
