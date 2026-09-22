"""Unit tests for RequirementPipeline and Planning model integration."""

import pytest
from app.agents.requirement_agent import RequirementAgent, RequirementPipeline
from app.models.planning import PlanningSpec, FloorPlanSpec, RoomSpec


@pytest.fixture
def agent():
    return RequirementAgent()


def test_pipeline_end_to_end_ready_for_planning(agent):
    brief = """
    15m x 20m plot, north-facing, 1 floor.
    Living room 25 sqm next to dining.
    Dining 15 sqm.
    Kitchen 12 sqm next to dining.
    Master bedroom 20 sqm with attached bathroom.
    Bathroom 6 sqm.
    """
    res = agent.process(brief)
    assert res.can_proceed_to_planning is True
    assert res.status == "READY_FOR_PLANNING"
    assert res.completeness.is_complete is True
    assert res.validation.is_valid is True
    assert "Ready for Planning" in res.summary()


def test_pipeline_end_to_end_needs_clarification(agent):
    brief = "Design a 2-storey house on a 15m x 20m plot. Ground floor has kitchen and living room."
    res = agent.process(brief)
    assert res.can_proceed_to_planning is False
    assert res.status == "NEEDS_CLARIFICATION"
    assert 2 in res.completeness.missing_floors
    assert len(res.completeness.clarification_questions) > 0


def test_pipeline_multi_turn_conversational_update(agent):
    """Multi-turn conversation flow:

    Turn 1: User provides partial brief missing Floor 2.
    Turn 2: User provides Floor 2 details.
    Pipeline becomes complete and ready for Planning!
    """
    # Turn 1
    turn1_input = "2-floor house, 15m x 20m plot. Ground floor: living room, dining room, kitchen."
    res1 = agent.process(turn1_input)
    assert res1.can_proceed_to_planning is False
    assert 2 in res1.completeness.missing_floors

    # Turn 2: supply Floor 2
    turn2_input = "Floor 2: 2 bedrooms and 1 bathroom."
    res2 = agent.update(res1.requirements, turn2_input)

    assert res2.can_proceed_to_planning is True
    assert res2.status == "READY_FOR_PLANNING"
    assert res2.completeness.is_complete is True
    assert len(res2.requirements.floors) == 2

    # Verify Floor 1 rooms were preserved
    f1_types = {r.room_type for r in res2.requirements.get_floor(1).room_requirements}
    assert "living" in f1_types
    assert "dining" in f1_types
    assert "kitchen" in f1_types

    # Verify Floor 2 rooms were added
    f2_types = {r.room_type for r in res2.requirements.get_floor(2).room_requirements}
    assert "bedroom" in f2_types
    assert "bathroom" in f2_types


def test_integration_compatibility_with_planning_models(agent):
    """Verify Requirements produced by RequirementAgent can be seamlessly transformed

    into PlanningSpec / RoomSpec without requiring geometry or ASAA logic.
    """
    brief = """
    15m x 20m plot, 2 floors.
    Ground floor: living room 20 sqm, kitchen 10 sqm.
    Floor 2: 2 bedrooms 15 sqm each, 1 bathroom 5 sqm.
    """
    reqs = agent.parse(brief)

    # Transform Requirements into PlanningSpec
    floor_specs = []
    for f in reqs.floors:
        room_specs = []
        for r in f.room_requirements:
            category = "private" if "bedroom" in r.room_type or "bath" in r.room_type else "social"
            room_specs.append(
                RoomSpec(
                    room_type=r.room_type,
                    room_category=category,
                    floor_number=f.floor_number,
                    count=r.min_count,
                    target_area_sqm=r.preferred_area_sqm or 15.0,
                    adjacency=r.adjacency,
                    avoid=r.separation,
                    source_requirement_id=r.id,
                )
            )
        floor_specs.append(
            FloorPlanSpec(
                floor_number=f.floor_number,
                floor_name=f.floor_name,
                room_specs=room_specs,
                staircase_intent={"required": f.staircase_required},
            )
        )

    planning_spec = PlanningSpec(
        project_name=reqs.project_name,
        floors=floor_specs,
        source_requirements_id=reqs.id,
    )

    assert len(planning_spec.floors) == 2
    assert len(planning_spec.all_room_specs()) == 4
    assert planning_spec.total_target_area() > 0
