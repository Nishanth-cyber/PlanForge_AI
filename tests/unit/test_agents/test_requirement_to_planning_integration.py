"""Integration test: Requirement Agent -> Planning Agent -> PlanningSpec.

Realistic multi-floor scenario demonstrating end-to-end flow from natural language
to fully-structured PlanningSpec ready for ASAA spatial allocation.
"""

import pytest
from app.agents.requirement_agent import RequirementAgent
from app.agents.planning_agent import PlanningAgent
from app.models.planning import PlanningSpec


def test_realistic_two_floor_flow():
    req_agent = RequirementAgent()
    planning_agent = PlanningAgent()

    user_brief = """
    Design a two-floor house on a 30 feet by 40 feet north-facing plot.
    Entrance from north to living room.

    Ground Floor:
    Living room 250 sq ft next to dining.
    Dining room 150 sq ft next to kitchen.
    Kitchen 120 sq ft.
    Bedroom 140 sq ft.
    Bathroom 50 sq ft.

    Floor 2:
    Master bedroom 220 sq ft with attached bathroom.
    Bathroom 60 sq ft.
    Bedroom 130 sq ft.
    Study room 100 sq ft.
    """

    # 1. Parse into structured Requirements
    reqs = req_agent.parse(user_brief, project_name="Sharma Residence")
    assert reqs.target_floors == 2
    assert reqs.plot_dimensions is not None
    assert len(reqs.floors) == 2
    assert reqs.orientation == "north"
    assert reqs.entrance_facing == "north"

    # 2. Plan into PlanningSpec
    plan_spec = planning_agent.plan(reqs)
    assert isinstance(plan_spec, PlanningSpec)
    assert plan_spec.project_name == "Sharma Residence"
    assert len(plan_spec.floors) == 2

    # Verify Floor 1
    f1 = plan_spec.get_floor(1)
    assert f1 is not None
    f1_types = {r.room_type for r in f1.room_specs}
    assert f1_types == {"living", "dining", "kitchen", "bedroom", "bathroom"}
    f1_spec_zones = f1.circulation_zones
    assert "public_circulation" in f1_spec_zones
    assert "service_circulation" in f1_spec_zones
    assert "vertical_circulation" in f1_spec_zones
    assert f1.entrance_intent is not None
    assert f1.entrance_intent["facing"] == "north"
    assert f1.entrance_intent["preferred_room"] == "living"
    assert f1.staircase_intent is not None
    assert f1.staircase_intent["connects_floors"] == [1, 2]

    # Verify Floor 1 relationships
    assert "dining" in f1.adjacency_matrix["living"]
    assert "living" in f1.adjacency_matrix["dining"]
    assert "kitchen" in f1.adjacency_matrix["dining"]
    assert "dining" in f1.adjacency_matrix["kitchen"]

    # Verify Floor 2
    f2 = plan_spec.get_floor(2)
    assert f2 is not None
    f2_types = {r.room_type for r in f2.room_specs}
    assert f2_types == {"master_bedroom", "bedroom", "study", "bathroom"}
    assert "private_circulation" in f2.circulation_zones
    assert "vertical_circulation" in f2.circulation_zones
    assert f2.entrance_intent is None  # No entrance on floor 2
    assert f2.staircase_intent is not None

    # Verify Floor 2 attached bathroom link
    f2_rooms = {r.room_type: r for r in f2.room_specs}
    mbr = f2_rooms["master_bedroom"]
    bath = f2_rooms["bathroom"]
    assert bath.attached_to_room_id == mbr.id
    assert "bathroom" in f2.adjacency_matrix["master_bedroom"]
    assert "master_bedroom" in f2.adjacency_matrix["bathroom"]

    # Verify priorities
    assert mbr.priority == "high"
    f1_rooms = {r.room_type: r for r in f1.room_specs}
    assert f1_rooms["living"].priority == "high"
    assert f1_rooms["kitchen"].priority == "high"
    assert f1_rooms["bedroom"].priority == "normal"

    # Verify strict boundary invariants: NO GEOMETRY
    for f in plan_spec.floors:
        assert not hasattr(f, "polygon")
        assert not hasattr(f, "bounds")
        for r in f.room_specs:
            assert not hasattr(r, "x")
            assert not hasattr(r, "y")
            assert not hasattr(r, "polygon")
            assert not hasattr(r, "centroid")
