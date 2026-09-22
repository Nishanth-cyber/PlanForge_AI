"""Unit tests for app.agents.planning_agent.agent — PlanningAgent."""

import pytest
from app.agents.planning_agent import PlanningAgent, IncompleteRequirementsError
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.models.planning import PlanningSpec, FloorPlanSpec, RoomSpec


@pytest.fixture
def planner():
    return PlanningAgent()


@pytest.fixture
def valid_single_floor_reqs():
    f1 = FloorRequirement(
        floor_number=1,
        floor_name="Ground Floor",
        room_requirements=[
            RoomRequirement(room_type="living", min_count=1, preferred_area_sqm=25.0),
            RoomRequirement(room_type="dining", min_count=1, preferred_area_sqm=15.0),
            RoomRequirement(room_type="kitchen", min_count=1, preferred_area_sqm=12.0),
            RoomRequirement(room_type="master_bedroom", min_count=1, preferred_area_sqm=20.0),
            RoomRequirement(room_type="bathroom", min_count=1, preferred_area_sqm=6.0, attached_to="master_bedroom"),
        ],
    )
    return Requirements(
        project_name="Single Story Villa",
        plot_dimensions=(15.0, 20.0),
        plot_area_sqm=300.0,
        orientation="north",
        entrance_facing="north",
        target_floors=1,
        floors=[f1],
    )


@pytest.fixture
def valid_two_floor_reqs():
    f1 = FloorRequirement(
        floor_number=1,
        floor_name="Ground Floor",
        room_requirements=[
            RoomRequirement(room_type="living", min_count=1, preferred_area_sqm=25.0),
            RoomRequirement(room_type="dining", min_count=1, preferred_area_sqm=15.0),
            RoomRequirement(room_type="kitchen", min_count=1, preferred_area_sqm=12.0),
        ],
    )
    f2 = FloorRequirement(
        floor_number=2,
        floor_name="First Floor",
        room_requirements=[
            RoomRequirement(room_type="master_bedroom", min_count=1, preferred_area_sqm=22.0),
            RoomRequirement(room_type="bedroom", min_count=1, preferred_area_sqm=16.0),
            RoomRequirement(room_type="study", min_count=1, preferred_area_sqm=10.0),
        ],
        staircase_required=True,
    )
    return Requirements(
        project_name="Duplex House",
        plot_dimensions=(15.0, 20.0),
        plot_area_sqm=300.0,
        target_floors=2,
        floors=[f1, f2],
    )


class TestBasicPlanning:
    def test_requirements_to_planning_spec(self, planner, valid_single_floor_reqs):
        spec = planner.plan(valid_single_floor_reqs)
        assert isinstance(spec, PlanningSpec)
        assert spec.project_name == "Single Story Villa"
        assert spec.source_requirements_id == valid_single_floor_reqs.id
        assert len(spec.floors) == 1
        assert len(spec.floors[0].room_specs) == 5

    def test_room_identity_traceability(self, planner, valid_single_floor_reqs):
        """Every RoomSpec must trace back to its source RoomRequirement ID."""
        spec = planner.plan(valid_single_floor_reqs)
        f1_req = valid_single_floor_reqs.floors[0]
        req_ids = {r.id for r in f1_req.room_requirements}

        for room_spec in spec.floors[0].room_specs:
            assert room_spec.id is not None
            assert room_spec.source_requirement_id in req_ids

    def test_room_category_normalization(self, planner, valid_single_floor_reqs):
        spec = planner.plan(valid_single_floor_reqs)
        categories = {r.room_type: r.room_category for r in spec.floors[0].room_specs}

        assert categories["living"] == "social"
        assert categories["dining"] == "social"
        assert categories["kitchen"] == "service"
        assert categories["master_bedroom"] == "private"
        assert categories["bathroom"] == "service"

    def test_floor_assignment_preservation(self, planner, valid_two_floor_reqs):
        """Planning must preserve exact floor distribution without moving rooms."""
        spec = planner.plan(valid_two_floor_reqs)
        assert len(spec.floors) == 2

        f1_types = {r.room_type for r in spec.floors[0].room_specs}
        f2_types = {r.room_type for r in spec.floors[1].room_specs}

        assert f1_types == {"living", "dining", "kitchen"}
        assert f2_types == {"master_bedroom", "bedroom", "study"}

    def test_room_count_and_target_area_preservation(self, planner, valid_single_floor_reqs):
        spec = planner.plan(valid_single_floor_reqs)
        room_map = {r.room_type: r for r in spec.floors[0].room_specs}

        assert room_map["living"].target_area_sqm == 25.0
        assert room_map["dining"].target_area_sqm == 15.0
        assert room_map["kitchen"].target_area_sqm == 12.0
        assert room_map["master_bedroom"].target_area_sqm == 20.0
        assert room_map["bathroom"].target_area_sqm == 6.0


class TestPriorities:
    def test_priority_assignment(self, planner, valid_single_floor_reqs):
        spec = planner.plan(valid_single_floor_reqs)
        priorities = {r.room_type: r.priority for r in spec.floors[0].room_specs}

        assert priorities["living"] == "high"
        assert priorities["master_bedroom"] == "high"
        assert priorities["kitchen"] == "high"
        assert priorities["dining"] == "normal"
        assert priorities["bathroom"] == "normal"

    def test_priority_rationale(self, planner, valid_single_floor_reqs):
        spec = planner.plan(valid_single_floor_reqs)
        for r in spec.floors[0].room_specs:
            assert r.priority_rationale != ""
            assert len(r.priority_rationale) > 10


class TestIncompleteGating:
    def test_rejects_incomplete_missing_plot(self, planner):
        incomplete = Requirements(
            target_floors=1,
            floors=[FloorRequirement(floor_number=1, room_requirements=[RoomRequirement(room_type="living")])],
        )
        with pytest.raises(IncompleteRequirementsError) as exc_info:
            planner.plan(incomplete)
        assert "Cannot plan incomplete requirements" in str(exc_info.value)
        assert "plot_dimensions" in str(exc_info.value)

    def test_rejects_incomplete_unspecified_floor_2(self, planner):
        """Must reject when Floor 2 room requirements are missing."""
        incomplete = Requirements(
            plot_dimensions=(15.0, 20.0),
            target_floors=2,
            floors=[
                FloorRequirement(floor_number=1, room_requirements=[RoomRequirement(room_type="living")]),
                FloorRequirement(floor_number=2, room_requirements=[]),  # Empty!
            ],
        )
        with pytest.raises(IncompleteRequirementsError) as exc_info:
            planner.plan(incomplete)
        assert "Cannot plan incomplete requirements" in str(exc_info.value)


class TestDeterminism:
    def test_deterministic_output(self, planner, valid_single_floor_reqs):
        spec1 = planner.plan(valid_single_floor_reqs)
        spec2 = planner.plan(valid_single_floor_reqs)

        f1_rooms1 = [(r.room_type, r.priority, r.target_area_sqm) for r in spec1.floors[0].room_specs]
        f1_rooms2 = [(r.room_type, r.priority, r.target_area_sqm) for r in spec2.floors[0].room_specs]
        assert f1_rooms1 == f1_rooms2
        assert spec1.floors[0].adjacency_matrix == spec2.floors[0].adjacency_matrix
        assert spec1.floors[0].avoid_matrix == spec2.floors[0].avoid_matrix
