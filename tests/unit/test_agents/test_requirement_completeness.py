"""Unit tests for CompletenessGate — multi-floor gating, status, and no-invention checks."""

import pytest
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.agents.requirement_agent.completeness_gate import (
    CompletenessGate,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_INVALID,
)


@pytest.fixture
def gate():
    return CompletenessGate()


def test_complete_single_floor_requirements(gate):
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living"),
                    RoomRequirement(room_type="bedroom"),
                ],
            )
        ],
    )
    res = gate.check(reqs)
    assert res.is_complete is True
    assert res.can_proceed is True
    assert res.status == STATUS_COMPLETE
    assert res.missing_fields == []
    assert res.missing_floors == []


def test_incomplete_missing_plot(gate):
    reqs = Requirements(
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="bedroom")],
            )
        ],
    )
    res = gate.check(reqs)
    assert res.is_complete is False
    assert res.can_proceed is False
    assert "plot_dimensions" in res.missing_fields
    assert len(res.clarification_questions) > 0


def test_incomplete_missing_target_floors(gate):
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="bedroom")],
            )
        ],
    )
    res = gate.check(reqs)
    assert res.is_complete is False
    assert "target_floors" in res.missing_fields


def test_multi_floor_gating_unspecified_floor_2_is_incomplete(gate):
    """User requests 2 floors, but Floor 2 has no room requirements.

    Must NOT invent Floor 2 rooms! Must block and ask for Floor 2 details.
    """
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=2,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living"),
                    RoomRequirement(room_type="kitchen"),
                ],
            ),
            FloorRequirement(
                floor_number=2,
                room_requirements=[],  # Unspecified!
            ),
        ],
    )
    res = gate.check(reqs)
    assert res.is_complete is False
    assert res.can_proceed is False
    assert res.status == STATUS_INCOMPLETE
    assert 2 in res.missing_floors
    assert any("Floor 2" in q for q in res.clarification_questions)
    # Crucial guarantee: checking completeness does NOT mutate requirements
    assert len(reqs.floors[1].room_requirements) == 0


def test_multi_floor_gating_all_floors_specified_is_complete(gate):
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=2,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="living")],
            ),
            FloorRequirement(
                floor_number=2,
                room_requirements=[RoomRequirement(room_type="bedroom")],
            ),
        ],
    )
    res = gate.check(reqs)
    assert res.is_complete is True
    assert res.can_proceed is True
    assert res.missing_floors == []


def test_suggestions_strictly_opt_in(gate):
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=2,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="living")],
            ),
            FloorRequirement(
                floor_number=2,
                room_requirements=[],
            ),
        ],
    )
    # Default: allow_suggestions=False
    res_no_opt = gate.check(reqs, allow_suggestions=False)
    assert res_no_opt.suggestions == []

    # Opted-in: allow_suggestions=True
    res_opt = gate.check(reqs, allow_suggestions=True)
    assert len(res_opt.suggestions) > 0
    # Still does not mutate requirements object
    assert len(reqs.floors[1].room_requirements) == 0


def test_invalid_status_negative_dimensions(gate):
    reqs = Requirements(
        plot_dimensions=(-10.0, 20.0),
        target_floors=1,
    )
    res = gate.check(reqs)
    assert res.status == STATUS_INVALID
    assert res.can_proceed is False
