"""Unit tests for Requirements data contracts."""

import pytest
from app.models.requirements import RoomRequirement, FloorRequirement, Requirements
from app.utils.ids import generate_id


def test_room_requirement_defaults():
    """Test RoomRequirement default fields and ID generation."""
    req = RoomRequirement(room_type="bedroom")
    assert req.id is not None
    assert req.room_type == "bedroom"
    assert req.min_count == 1
    assert req.max_count is None
    assert req.adjacency == []
    assert req.separation == []
    assert req.source == "user"


def test_room_requirement_with_separation_and_attached():
    """Test RoomRequirement with avoidance and attached room relationships."""
    req = RoomRequirement(
        room_type="master_bedroom",
        min_count=1,
        min_area_sqm=16.0,
        preferred_area_sqm=20.0,
        adjacency=["walk_in_closet"],
        separation=["garage"],
        attached_to="ensuite",
    )
    assert req.preferred_area_sqm == 20.0
    assert "garage" in req.separation
    assert req.attached_to == "ensuite"


def test_floor_requirement_total_rooms():
    """Test FloorRequirement total_rooms calculation."""
    floor = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living", min_count=1),
            RoomRequirement(room_type="kitchen", min_count=1),
            RoomRequirement(room_type="bedroom", min_count=2),
        ],
    )
    assert floor.total_rooms() == 4


def test_requirements_total_rooms_multi_floor():
    """Test Requirements.total_rooms across multiple floors (fixes old bug)."""
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living", min_count=1),
            RoomRequirement(room_type="kitchen", min_count=1),
        ],
    )
    f2 = FloorRequirement(
        floor_number=2,
        room_requirements=[
            RoomRequirement(room_type="bedroom", min_count=3),
            RoomRequirement(room_type="bathroom", min_count=2),
        ],
    )
    reqs = Requirements(
        project_name="Duplex Villa",
        floors=[f1, f2],
    )
    assert reqs.total_rooms() == 7
    assert reqs.has_requirements_for_floor(1) is True
    assert reqs.has_requirements_for_floor(2) is True
    assert reqs.has_requirements_for_floor(3) is False
    assert reqs.get_floor(1) == f1
    assert reqs.get_floor(2) == f2
    assert reqs.get_floor(99) is None
    assert len(reqs.all_room_requirements()) == 4


def test_requirements_plot_and_setbacks():
    """Test plot dimensions, boundary polygon, and setback requirements."""
    reqs = Requirements(
        project_name="Modern Home",
        plot_area_sqm=300.0,
        plot_dimensions=(15.0, 20.0),
        plot_shape=((0.0, 0.0), (15.0, 0.0), (15.0, 20.0), (0.0, 20.0)),
        setbacks={"front": 3.0, "rear": 2.0, "left": 1.5, "right": 1.5},
        orientation="north",
        entrance_facing="east",
        entrance_room_type="living",
    )
    assert reqs.plot_area_sqm == 300.0
    assert reqs.plot_dimensions == (15.0, 20.0)
    assert len(reqs.plot_shape) == 4
    assert reqs.setbacks["front"] == 3.0
    assert reqs.orientation == "north"
    assert reqs.entrance_facing == "east"


# ---------------------------------------------------------------------------
# Edge-case / invalid-input behaviour
# ---------------------------------------------------------------------------

def test_room_requirement_zero_area_bounds_are_none_by_default():
    """min/max/preferred area fields default to None (no invented area)."""
    req = RoomRequirement(room_type="storage")
    assert req.min_area_sqm is None
    assert req.max_area_sqm is None
    assert req.preferred_area_sqm is None


def test_room_requirement_source_defaults_to_user():
    """Source field defaults to 'user' and can be overridden."""
    req_user = RoomRequirement(room_type="kitchen")
    req_derived = RoomRequirement(room_type="hallway", source="derived")
    req_default = RoomRequirement(room_type="lobby", source="default")
    assert req_user.source == "user"
    assert req_derived.source == "derived"
    assert req_default.source == "default"


def test_room_requirement_empty_adjacency_and_separation():
    """Adjacency and separation lists default to empty; no cross-contamination."""
    r1 = RoomRequirement(room_type="bedroom", adjacency=["bathroom"])
    r2 = RoomRequirement(room_type="kitchen")
    assert r2.adjacency == []
    assert r2.separation == []
    # Verify mutable default does not share state across instances
    assert r1.adjacency is not r2.adjacency


def test_floor_requirement_staircase_flag():
    """FloorRequirement staircase_required flag defaults False; can be set True."""
    f_no_stair = FloorRequirement(floor_number=1)
    f_with_stair = FloorRequirement(floor_number=2, staircase_required=True)
    assert f_no_stair.staircase_required is False
    assert f_with_stair.staircase_required is True


def test_floor_requirement_total_rooms_zero_when_no_rooms():
    """total_rooms() must return 0 when the floor has no room requirements."""
    f = FloorRequirement(floor_number=1)
    assert f.total_rooms() == 0


def test_requirements_total_rooms_zero_when_no_floors():
    """total_rooms() must return 0 on Requirements with no floors."""
    reqs = Requirements(project_name="Empty")
    assert reqs.total_rooms() == 0


def test_requirements_has_requirements_for_floor_false_when_no_rooms():
    """A floor with no room_requirements returns False for has_requirements_for_floor."""
    f = FloorRequirement(floor_number=1, room_requirements=[])
    reqs = Requirements(project_name="Bare", floors=[f])
    assert reqs.has_requirements_for_floor(1) is False


def test_requirements_all_room_requirements_empty():
    """all_room_requirements() returns an empty list if no rooms are defined."""
    reqs = Requirements(project_name="Empty Plot")
    assert reqs.all_room_requirements() == []


def test_requirements_unique_ids():
    """Each Requirements, FloorRequirement, and RoomRequirement gets a unique ID."""
    reqs1 = Requirements()
    reqs2 = Requirements()
    assert reqs1.id != reqs2.id

    fr1 = FloorRequirement()
    fr2 = FloorRequirement()
    assert fr1.id != fr2.id

    rr1 = RoomRequirement()
    rr2 = RoomRequirement()
    assert rr1.id != rr2.id


def test_room_requirement_with_max_count():
    """max_count can be set and is preserved on the model."""
    req = RoomRequirement(room_type="bedroom", min_count=2, max_count=4)
    assert req.min_count == 2
    assert req.max_count == 4


def test_requirements_target_floors_and_notes():
    """target_floors and notes fields are stored correctly."""
    reqs = Requirements(
        project_name="Bungalow",
        target_floors=1,
        notes="Single-story accessible home",
        raw_input="I want a 1-storey accessible home with 2 bedrooms",
    )
    assert reqs.target_floors == 1
    assert "accessible" in reqs.notes
    assert reqs.raw_input != ""
