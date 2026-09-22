"""Unit tests for Planning data contracts."""

from app.models.planning import RoomSpec, FloorPlanSpec, PlanningSpec


def test_room_spec_creation():
    """Test RoomSpec creation with category, priority, and avoid relations."""
    r = RoomSpec(
        room_type="kitchen",
        room_category="service",
        floor_number=1,
        count=1,
        target_area_sqm=12.0,
        min_area_sqm=10.0,
        max_area_sqm=15.0,
        adjacency=["dining"],
        avoid=["bedroom", "bathroom"],
        priority="high",
    )
    assert r.id is not None
    assert r.room_category == "service"
    assert r.priority == "high"
    assert "dining" in r.adjacency
    assert "bedroom" in r.avoid


def test_floor_plan_spec():
    """Test FloorPlanSpec circulation zones, intent dictionaries, and room list."""
    spec = FloorPlanSpec(
        floor_number=1,
        floor_name="Ground Floor",
        total_area_sqm=100.0,
        room_specs=[
            RoomSpec(room_type="living", target_area_sqm=25.0),
            RoomSpec(room_type="dining", target_area_sqm=15.0),
        ],
        circulation_zones=["foyer_hallway"],
        circulation_notes="Central corridor with entrance foyer",
        adjacency_matrix={"living": ["dining"], "dining": ["living"]},
        avoid_matrix={"dining": ["toilet"]},
        entrance_intent={"preferred_room": "living", "facing": "north"},
        staircase_intent={"required": True, "connects_floors": [1, 2]},
    )
    assert len(spec.room_specs) == 2
    assert spec.entrance_intent["facing"] == "north"
    assert spec.staircase_intent["required"] is True


def test_planning_spec_lookups_and_area():
    """Test PlanningSpec helper methods for floor lookup, all room specs, and total area."""
    r1 = RoomSpec(room_type="living", count=1, target_area_sqm=30.0)
    r2 = RoomSpec(room_type="kitchen", count=1, target_area_sqm=15.0)
    r3 = RoomSpec(room_type="bedroom", count=2, target_area_sqm=14.0)

    f1 = FloorPlanSpec(floor_number=1, room_specs=[r1, r2])
    f2 = FloorPlanSpec(floor_number=2, room_specs=[r3])

    plan = PlanningSpec(
        project_name="Two Story House",
        floors=[f1, f2],
        global_constraints={"max_ground_coverage": 0.6},
    )

    assert plan.get_floor(1) == f1
    assert plan.get_floor(2) == f2
    assert plan.get_floor(3) is None
    assert len(plan.all_room_specs()) == 3
    assert plan.get_room_by_id(r1.id) == r1
    assert plan.get_room_by_id("non_existent_id") is None
    # total_target_area: 30*1 + 15*1 + 14*2 = 73.0
    assert plan.total_target_area() == 73.0
