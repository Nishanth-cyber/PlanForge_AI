"""Unit tests for circulation, entrance intent, staircase intent, and global constraints."""

import pytest
from app.agents.planning_agent import PlanningAgent
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement


@pytest.fixture
def planner():
    return PlanningAgent()


def test_circulation_zones_identification(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living"),
            RoomRequirement(room_type="dining"),
            RoomRequirement(room_type="kitchen"),
            RoomRequirement(room_type="bedroom"),
        ],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    f1_spec = spec.floors[0]

    assert "public_circulation" in f1_spec.circulation_zones
    assert "private_circulation" in f1_spec.circulation_zones
    assert "service_circulation" in f1_spec.circulation_zones
    assert len(f1_spec.circulation_notes) > 0


def test_entrance_intent_on_floor_1(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="living")],
    )
    f2 = FloorRequirement(
        floor_number=2,
        room_requirements=[RoomRequirement(room_type="bedroom")],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        orientation="north",
        entrance_facing="east",
        entrance_room_type="living",
        target_floors=2,
        floors=[f1, f2],
    )
    spec = planner.plan(reqs)

    # Floor 1 must have entrance intent
    assert spec.floors[0].entrance_intent is not None
    assert spec.floors[0].entrance_intent["facing"] == "east"
    assert spec.floors[0].entrance_intent["preferred_room"] == "living"

    # Floor 2 must NOT have entrance intent
    assert spec.floors[1].entrance_intent is None


def test_staircase_intent_multi_floor(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="living")],
    )
    f2 = FloorRequirement(
        floor_number=2,
        room_requirements=[RoomRequirement(room_type="bedroom")],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=2,
        floors=[f1, f2],
    )
    spec = planner.plan(reqs)

    # Both floors must have staircase vertical connectivity intent
    for fn, f_spec in enumerate(spec.floors, start=1):
        assert f_spec.staircase_intent is not None
        assert f_spec.staircase_intent["required"] is True
        assert f_spec.staircase_intent["connects_floors"] == [1, 2]
        assert f_spec.staircase_intent["alignment_required"] is True
        assert "vertical_circulation" in f_spec.circulation_zones


def test_staircase_intent_single_floor_absent(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="living")],
        staircase_required=False,
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    assert spec.floors[0].staircase_intent is None


def test_global_constraints_formulation(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[RoomRequirement(room_type="living")],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        plot_area_sqm=300.0,
        orientation="north",
        setbacks={"front": 3.0, "rear": 2.0},
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    gc = spec.global_constraints

    assert gc["plot_dimensions"] == (15.0, 20.0)
    assert gc["plot_area_sqm"] == 300.0
    assert gc["orientation"] == "north"
    assert gc["setbacks"] == {"front": 3.0, "rear": 2.0}
    assert gc["privacy_buffering"] is True
    assert gc["circulation_continuity"] is True
