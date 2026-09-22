"""Unit tests for RequirementValidator — semantic validation of structured Requirements."""

import pytest
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.agents.requirement_agent.validator import RequirementValidator


@pytest.fixture
def validator():
    return RequirementValidator()


def test_valid_requirements(validator):
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        plot_area_sqm=300.0,
        orientation="north",
        entrance_facing="east",
        setbacks={"front": 3.0, "rear": 2.0, "left": 1.5, "right": 1.5},
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(
                        room_type="living",
                        min_count=1,
                        preferred_area_sqm=25.0,
                        adjacency=["dining"],
                    ),
                    RoomRequirement(
                        room_type="dining",
                        min_count=1,
                        preferred_area_sqm=15.0,
                    ),
                ],
            )
        ],
    )
    res = validator.validate(reqs)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_invalid_plot_dimensions_and_area(validator):
    reqs = Requirements(
        plot_dimensions=(-5.0, 20.0),
        plot_area_sqm=-100.0,
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    err_fields = [e.field for e in res.errors]
    assert "plot_dimensions" in err_fields
    assert "plot_area_sqm" in err_fields


def test_setbacks_exceeding_plot_dimensions(validator):
    reqs = Requirements(
        plot_dimensions=(10.0, 10.0),
        setbacks={"front": 6.0, "rear": 5.0},  # 11m >= 10m depth
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    assert any("setbacks" in e.field for e in res.errors)


def test_inverted_area_range(validator):
    reqs = Requirements(
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(
                        room_type="bedroom",
                        min_area_sqm=20.0,
                        max_area_sqm=15.0,  # min > max!
                    )
                ],
            )
        ]
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    assert any("area_range" in e.field for e in res.errors)


def test_preferred_area_outside_min_max_bounds(validator):
    reqs = Requirements(
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(
                        room_type="bedroom",
                        min_area_sqm=12.0,
                        preferred_area_sqm=25.0,
                        max_area_sqm=20.0,  # preferred > max!
                    )
                ],
            )
        ]
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    assert any("preferred_area_sqm" in e.field for e in res.errors)


def test_negative_room_count_or_inverted_max_count(validator):
    reqs = Requirements(
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="bedroom", min_count=0),
                    RoomRequirement(room_type="kitchen", min_count=2, max_count=1),
                ],
            )
        ]
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    err_fields = [e.field for e in res.errors]
    assert "min_count" in err_fields
    assert "max_count" in err_fields


def test_self_adjacency_and_separation(validator):
    reqs = Requirements(
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(
                        room_type="bedroom",
                        adjacency=["bedroom"],  # self-adjacency!
                    ),
                    RoomRequirement(
                        room_type="kitchen",
                        separation=["kitchen"],  # self-separation!
                    ),
                    RoomRequirement(
                        room_type="dining",
                        adjacency=["living"],
                        separation=["living"],  # conflicting!
                    ),
                ],
            )
        ]
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    err_fields = [e.field for e in res.errors]
    assert "adjacency" in err_fields
    assert "separation" in err_fields
    assert "relationships" in err_fields


def test_non_contiguous_floor_numbering(validator):
    reqs = Requirements(
        floors=[
            FloorRequirement(floor_number=1, room_requirements=[RoomRequirement(room_type="living")]),
            FloorRequirement(floor_number=3, room_requirements=[RoomRequirement(room_type="bedroom")]),  # gap!
        ]
    )
    res = validator.validate(reqs)
    assert res.is_valid is False
    assert any("floors" in e.field for e in res.errors)
