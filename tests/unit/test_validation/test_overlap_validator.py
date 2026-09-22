"""Unit tests for OverlapValidator: room-room and room-staircase collision detection."""

import pytest
from app.models.geometry import Geometry, GeoRoom, GeoStaircase
from app.validation.overlap_validator import OverlapValidator


def test_overlap_validator_adjacent_rooms_pass():
    """Verify clean touching rooms sharing boundary do NOT trigger overlap error."""
    # Room 1: (0, 0) to (4, 4)
    r1 = GeoRoom(id="r1", room_type="living", built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])
    # Room 2: (4, 0) to (8, 4) - touching at line x=4
    r2 = GeoRoom(id="r2", room_type="dining", built_polygon=[(4, 0), (8, 0), (8, 4), (4, 4)])

    geom = Geometry(rooms=[r1, r2], floor_number=1)
    val = OverlapValidator()
    issues = val.validate(geom)

    assert len(issues) == 0


def test_overlap_validator_room_intersection_error():
    """Verify error when two rooms collide with significant intersection area."""
    # Room 1: (0, 0) to (5, 5)
    r1 = GeoRoom(id="r1", room_type="bedroom", built_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])
    # Room 2: (3, 0) to (8, 5) - overlaps (3..5, 0..5) -> 2m x 5m = 10 sqm!
    r2 = GeoRoom(id="r2", room_type="bathroom", built_polygon=[(3, 0), (8, 0), (8, 5), (3, 5)])

    geom = Geometry(rooms=[r1, r2], floor_number=1)
    val = OverlapValidator()
    issues = val.validate(geom)

    assert len(issues) >= 1
    issue = issues[0]
    assert issue.severity == "error"
    assert issue.category == "overlap"
    assert issue.check == "room_overlap"
    assert issue.details["room_1_id"] == "r1"
    assert issue.details["room_2_id"] == "r2"
    assert issue.details["overlap_area_sqm"] == 10.0


def test_overlap_validator_staircase_room_collision():
    """Verify error when staircase footprint overlaps with a habitable room."""
    room = GeoRoom(id="r_bed", room_type="bedroom", built_polygon=[(0, 0), (6, 0), (6, 6), (0, 6)])
    # Staircase inside bedroom: (2..4, 2..6)
    stair = GeoStaircase(id="stair_1", polygon=[(2, 2), (4, 2), (4, 6), (2, 6)])

    geom = Geometry(rooms=[room], staircases=[stair], floor_number=1)
    val = OverlapValidator()
    issues = val.validate(geom)

    assert any(i.check == "staircase_room_overlap" for i in issues)
