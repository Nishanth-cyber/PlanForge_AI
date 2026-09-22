"""Unit tests for RelationshipValidator: required/preferred adjacencies, separation, and attached suites."""

import pytest
from app.models.geometry import Geometry, GeoDoor, GeoRoom, GeoWall
from app.models.planning import FloorPlanSpec, RoomSpec
from app.models.requirements import FloorRequirements, RoomRequirement
from app.validation.relationship_validator import RelationshipValidator


def test_required_adjacency_satisfied_via_shared_wall():
    """Verify required adjacency passes when rooms share a boundary."""
    r1 = GeoRoom(id="r_liv", room_type="living", built_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])
    r2 = GeoRoom(id="r_din", room_type="dining", built_polygon=[(5, 0), (9, 0), (9, 5), (5, 5)])

    geom = Geometry(rooms=[r1, r2], floor_number=1)
    reqs = FloorRequirements(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="living", adjacency=["dining"])],
    )

    val = RelationshipValidator()
    issues = val.validate(geom, floor_reqs=reqs)
    assert len(issues) == 0


def test_required_adjacency_failed_error():
    """Verify error when required adjacency has no physical shared wall or door."""
    # Living and dining placed far apart
    r1 = GeoRoom(id="r_liv", room_type="living", built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])
    r2 = GeoRoom(id="r_din", room_type="dining", built_polygon=[(10, 0), (14, 0), (14, 4), (10, 4)])

    geom = Geometry(rooms=[r1, r2], floor_number=1)
    reqs = FloorRequirements(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="living", adjacency=["dining"])],
    )

    val = RelationshipValidator()
    issues = val.validate(geom, floor_reqs=reqs)

    assert len(issues) >= 1
    assert issues[0].severity == "error"
    assert issues[0].check == "required_adjacency"
    assert "Required adjacency between" in issues[0].message


def test_preferred_adjacency_produces_warning():
    """Verify preferred adjacency failure produces a warning rather than an error."""
    r1 = GeoRoom(id="r_din", room_type="dining", built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])
    r2 = GeoRoom(id="r_kit", room_type="kitchen", built_polygon=[(10, 0), (14, 0), (14, 4), (10, 4)])

    geom = Geometry(rooms=[r1, r2], floor_number=1)
    spec = FloorPlanSpec(
        floor_number=1,
        adjacency_matrix={"dining": ["kitchen"]},  # Planning preferred, not user required
    )

    val = RelationshipValidator()
    issues = val.validate(geom, floor_plan_spec=spec)

    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].check == "preferred_adjacency"


def test_separation_violation_error():
    """Verify error when rooms with an avoid/separation constraint touch."""
    # Bedroom and toilet have separation constraint, but share wall x=4
    r1 = GeoRoom(id="r_bed", room_type="bedroom", built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])
    r2 = GeoRoom(id="r_toilet", room_type="powder_room", built_polygon=[(4, 0), (7, 0), (7, 4), (4, 4)])

    geom = Geometry(rooms=[r1, r2], floor_number=1)
    reqs = FloorRequirements(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="bedroom", separation=["powder_room"])],
    )

    val = RelationshipValidator()
    issues = val.validate(geom, floor_reqs=reqs)

    assert any(i.check == "separation_violation" for i in issues)


def test_attached_suite_relationship_check():
    """Verify attached suite passes when connected and fails when isolated."""
    mb = GeoRoom(id="r_mb", room_type="master_bedroom", built_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])
    bath = GeoRoom(id="r_bath", room_type="bathroom", built_polygon=[(5, 0), (8, 0), (8, 5), (5, 5)])

    # 1. Attached: sharing wall -> passes
    geom_ok = Geometry(rooms=[mb, bath], floor_number=2)
    spec = FloorPlanSpec(
        floor_number=2,
        room_specs=[RoomSpec(room_type="bathroom", attached_to_room_id="spec_mb")],
    )

    val = RelationshipValidator()
    assert len(val.validate(geom_ok, floor_plan_spec=spec)) == 0

    # 2. Detached: placed far apart -> error
    bath_far = GeoRoom(id="r_bath_far", room_type="bathroom", built_polygon=[(15, 0), (18, 0), (18, 5), (15, 5)])
    geom_bad = Geometry(rooms=[mb, bath_far], floor_number=2)
    issues_bad = val.validate(geom_bad, floor_plan_spec=spec)

    assert any(i.check == "attached_suite_connection" for i in issues_bad)
