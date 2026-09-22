"""Unit tests for ConnectivityValidator."""

import pytest
from app.models.geometry import Geometry, GeoRoom, GeoWall, GeoDoor
from app.validation.connectivity_validator import ConnectivityValidator


def test_isolated_room_detection():
    """Verify that a room with no doors is flagged as isolated."""
    # Room 1: Living, Room 2: Bedroom (isolated)
    r1 = GeoRoom(id="r_living", room_type="living", usable_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)], area_sqm=25.0)
    r2 = GeoRoom(id="r_bed", room_type="bedroom", usable_polygon=[(5, 0), (10, 0), (10, 5), (5, 5)], area_sqm=25.0)
    
    # Exterior entrance into living room
    w_ext = GeoWall(id="w_ext", start=(0, 0), end=(5, 0), type="exterior", room_ids=["r_living"])
    door_ext = GeoDoor(id="d_ext", wall_id="w_ext", position=(2.5, 0), type="entrance")

    geom = Geometry(
        floor_number=1,
        rooms=[r1, r2],
        walls=[w_ext],
        doors=[door_ext],
    )

    validator = ConnectivityValidator()
    issues = validator.validate(geom)

    assert any(i.severity == "error" and i.check == "isolated_room" and i.room_id == "r_bed" for i in issues)


def test_missing_entrance_connection_floor_1():
    """Verify that Floor 1 without an exterior entrance door triggers missing_entrance_connection."""
    r1 = GeoRoom(id="r_living", room_type="living", usable_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)], area_sqm=25.0)
    r2 = GeoRoom(id="r_bed", room_type="bedroom", usable_polygon=[(5, 0), (10, 0), (10, 5), (5, 5)], area_sqm=25.0)
    
    # Shared interior wall and door between them, but NO entrance to outside
    w_int = GeoWall(id="w_int", start=(5, 0), end=(5, 5), type="interior", room_ids=["r_living", "r_bed"])
    d_int = GeoDoor(id="d_int", wall_id="w_int", position=(5, 2.5), type="standard")

    geom = Geometry(
        floor_number=1,
        rooms=[r1, r2],
        walls=[w_int],
        doors=[d_int],
    )

    validator = ConnectivityValidator()
    issues = validator.validate(geom)

    assert any(i.severity == "error" and i.check == "missing_entrance_connection" for i in issues)


def test_fully_connected_floor_passes():
    """Verify that a properly connected floor with entrance produces no errors."""
    r_living = GeoRoom(id="r_living", room_type="living", usable_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)], area_sqm=25.0)
    r_bed = GeoRoom(id="r_bed", room_type="bedroom", usable_polygon=[(5, 0), (10, 0), (10, 5), (5, 5)], area_sqm=25.0)

    w_ext = GeoWall(id="w_ext", start=(0, 0), end=(5, 0), type="exterior", room_ids=["r_living"])
    d_ext = GeoDoor(id="d_ext", wall_id="w_ext", position=(2.5, 0), type="entrance")

    w_int = GeoWall(id="w_int", start=(5, 0), end=(5, 5), type="interior", room_ids=["r_living", "r_bed"])
    d_int = GeoDoor(id="d_int", wall_id="w_int", position=(5, 2.5), type="standard")

    geom = Geometry(
        floor_number=1,
        rooms=[r_living, r_bed],
        walls=[w_ext, w_int],
        doors=[d_ext, d_int],
    )

    validator = ConnectivityValidator()
    issues = validator.validate(geom)

    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 0


def test_unreachable_social_space():
    """Verify that if a social room is connected in an isolated pocket not reachable from entrance, it's flagged."""
    r_foyer = GeoRoom(id="r_foyer", room_type="foyer", usable_polygon=[(0, 0), (3, 0), (3, 3), (0, 3)], area_sqm=9.0)
    r_bed = GeoRoom(id="r_bed", room_type="bedroom", usable_polygon=[(0, 3), (3, 3), (3, 6), (0, 6)], area_sqm=9.0)
    r_living = GeoRoom(id="r_living", room_type="living", usable_polygon=[(10, 0), (15, 0), (15, 5), (10, 5)], area_sqm=25.0)
    r_dining = GeoRoom(id="r_dining", room_type="dining", usable_polygon=[(10, 5), (15, 5), (15, 10), (10, 10)], area_sqm=25.0)

    # Entrance to foyer, door to bedroom
    w_ext = GeoWall(id="w_ext", start=(0, 0), end=(3, 0), type="exterior", room_ids=["r_foyer"])
    d_ext = GeoDoor(id="d_ext", wall_id="w_ext", position=(1.5, 0), type="entrance")

    w_foyer_bed = GeoWall(id="w_fb", start=(0, 3), end=(3, 3), type="interior", room_ids=["r_foyer", "r_bed"])
    d_fb = GeoDoor(id="d_fb", wall_id="w_foyer_bed", position=(1.5, 3), type="standard")

    # Living & Dining connected to each other, but not to foyer/entrance
    w_ld = GeoWall(id="w_ld", start=(10, 5), end=(15, 5), type="interior", room_ids=["r_living", "r_dining"])
    d_ld = GeoDoor(id="d_ld", wall_id="w_ld", position=(12.5, 5), type="standard")

    geom = Geometry(
        floor_number=1,
        rooms=[r_foyer, r_bed, r_living, r_dining],
        walls=[w_ext, w_foyer_bed, w_ld],
        doors=[d_ext, d_fb, d_ld],
    )

    validator = ConnectivityValidator()
    issues = validator.validate(geom)

    unreachable_checks = [i for i in issues if i.check == "unreachable_from_entrance"]
    assert len(unreachable_checks) >= 1
    unreached_ids = {i.room_id for i in unreachable_checks}
    assert "r_living" in unreached_ids or "r_dining" in unreached_ids
