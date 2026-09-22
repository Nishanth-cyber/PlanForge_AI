"""Unit tests for DoorValidator and WindowValidator: floating elements, wall attachments, orientations."""

import pytest
from app.models.architectural_design import ArchitecturalDesign, RoomDesign
from app.models.geometry import Geometry, GeoDoor, GeoRoom, GeoWall, GeoWindow
from app.models.windows import WindowIntent
from app.validation.door_validator import DoorValidator
from app.validation.window_validator import WindowValidator


def test_floating_door_detected():
    """Verify error when a door references a non-existent wall."""
    door = GeoDoor(
        id="door_bad",
        wall_id="non_existent_wall",
        position=(2.0, 0.0),
    )
    geom = Geometry(doors=[door], walls=[], floor_number=1)

    val = DoorValidator()
    issues = val.validate(geom)

    assert len(issues) >= 1
    assert issues[0].check == "floating_door"


def test_door_off_wall_detected():
    """Verify error when door coordinates are not located on the wall segment."""
    wall = GeoWall(id="w1", start=(0.0, 0.0), end=(5.0, 0.0), type="interior")
    door = GeoDoor(
        id="door_far",
        wall_id="w1",
        position=(2.5, 5.0),  # 5 meters away from the wall!
    )
    geom = Geometry(doors=[door], walls=[wall], floor_number=1)

    val = DoorValidator()
    issues = val.validate(geom)

    assert any(i.check == "door_off_wall" for i in issues)


def test_exterior_door_on_interior_wall_error():
    """Verify error when entrance door is placed on interior partition wall."""
    wall = GeoWall(id="w_int", start=(0.0, 0.0), end=(4.0, 0.0), type="interior")
    door = GeoDoor(
        id="d_ent",
        wall_id="w_int",
        position=(2.0, 0.0),
        type="entrance",
    )
    geom = Geometry(doors=[door], walls=[wall], floor_number=1)

    val = DoorValidator()
    issues = val.validate(geom)

    assert any(i.check == "exterior_door_on_interior_wall" for i in issues)


def test_window_on_interior_wall_error():
    """Verify error when window is placed on an interior partition wall."""
    wall = GeoWall(id="w_part", start=(0.0, 0.0), end=(4.0, 0.0), type="interior")
    window = GeoWindow(
        id="win_1",
        wall_id="w_part",
        position=(2.0, 0.0),
    )
    geom = Geometry(windows=[window], walls=[wall], floor_number=1)

    val = WindowValidator()
    issues = val.validate(geom)

    assert any(i.check == "window_on_interior_wall" for i in issues)


def test_window_orientation_mismatch_warning():
    """Verify warning when window orientation does not match intent."""
    # Wall from (0, 0) to (5, 0) has default CCW normal (0, 1) which is north
    wall = GeoWall(id="w_ext", start=(0.0, 0.0), end=(5.0, 0.0), type="exterior")
    window = GeoWindow(
        id="win_south",
        wall_id="w_ext",
        position=(2.5, 0.0),
        intent_id="intent_w_south",
    )
    geom = Geometry(windows=[window], walls=[wall], floor_number=1)

    # Intent requested south, but wall faces north
    floor_design = ArchitecturalDesign(
        floor_number=1,
        rooms=[
            RoomDesign(
                id="des_1",
                windows=[WindowIntent(id="intent_w_south", wall_orientation="south")],
            )
        ],
    )

    val = WindowValidator()
    issues = val.validate(geom, floor_design=floor_design)

    assert any(i.severity == "warning" and i.check == "window_orientation_mismatch" for i in issues)
