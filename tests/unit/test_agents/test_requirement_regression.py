"""Regression tests for known bugs in the previous PlanForge implementation.

1. Ordinal floor parsing must not crash ('1st floor', '2nd floor', '3rd floor').
2. Multiple rooms must not inherit the first room's area.
3. Missing Floor 1 header must not cause all room information to be discarded.
4. Missing Floor 2 requirements must NOT result in invented rooms (preventing old 'default_f2' bug).
5. No automatic default bedroom/study/bathroom injection.
"""

import pytest
from app.agents.requirement_agent import RequirementAgent, CompletenessGate


@pytest.fixture
def agent():
    return RequirementAgent()


def test_regression_bug1_ordinal_floor_parsing_no_crash(agent):
    """Old Bug 1: Ordinal floor tokens like '1st floor', '2nd floor', '3rd floor' caused regex crash."""
    brief = """
    30 x 40 plot, 3 floors.
    1st floor: living room, kitchen, dining room.
    2nd floor: 2 bedrooms, 1 bathroom.
    3rd floor: 1 study room, terrace.
    """
    reqs = agent.parse(brief)
    assert reqs.target_floors == 3
    assert len(reqs.floors) == 3
    assert reqs.get_floor(1) is not None
    assert reqs.get_floor(2) is not None
    assert reqs.get_floor(3) is not None

    f1_types = {r.room_type for r in reqs.get_floor(1).room_requirements}
    f2_types = {r.room_type for r in reqs.get_floor(2).room_requirements}
    f3_types = {r.room_type for r in reqs.get_floor(3).room_requirements}

    assert "living" in f1_types
    assert "kitchen" in f1_types
    assert "bedroom" in f2_types
    assert "study" in f3_types


def test_regression_bug2_room_area_bleeding_prevented(agent):
    """Old Bug 2: Multiple rooms inherited the first room's area.

    'Master bedroom 150 sq ft\nBedroom 120 sq ft\nStudy 80 sq ft' must NOT assign 150 sq ft to all rooms!
    """
    brief = """
    Plot 20m x 30m, 1 floor.
    Master bedroom 150 sq ft
    Bedroom 120 sq ft
    Study 80 sq ft
    """
    reqs = agent.parse(brief)
    f1 = reqs.get_floor(1)
    assert f1 is not None

    room_map = {r.room_type: r for r in f1.room_requirements}
    assert "master_bedroom" in room_map
    assert "bedroom" in room_map
    assert "study" in room_map

    sqft_to_sqm = 0.09290304
    mbr_area = room_map["master_bedroom"].preferred_area_sqm
    br_area = room_map["bedroom"].preferred_area_sqm
    study_area = room_map["study"].preferred_area_sqm

    assert mbr_area == pytest.approx(150 * sqft_to_sqm, rel=1e-3)
    assert br_area == pytest.approx(120 * sqft_to_sqm, rel=1e-3)
    assert study_area == pytest.approx(80 * sqft_to_sqm, rel=1e-3)

    # All three must have different, isolated area values
    assert mbr_area != br_area
    assert br_area != study_area


def test_regression_bug3_missing_floor_1_header_preserves_rooms(agent):
    """Old Bug 3: If user did not put a 'Floor 1:' header before describing ground floor rooms,

    the parser discarded all room information.
    """
    brief = """
    Plot 15m x 20m, 2 floors.
    Living room, dining room, kitchen, and master bedroom.
    Floor 2:
    2 bedrooms and 1 bathroom.
    """
    reqs = agent.parse(brief)
    f1 = reqs.get_floor(1)
    f2 = reqs.get_floor(2)

    assert f1 is not None
    assert f2 is not None

    f1_types = {r.room_type for r in f1.room_requirements}
    assert "living" in f1_types
    assert "kitchen" in f1_types
    assert "dining" in f1_types
    assert "master_bedroom" in f1_types

    f2_types = {r.room_type for r in f2.room_requirements}
    assert "bedroom" in f2_types
    assert "bathroom" in f2_types


def test_regression_bug4_missing_floor_2_does_not_invent_rooms(agent):
    """Old Bug 4: In the previous project, if user said:

    'Create a two-floor house. Ground floor has living room, dining room, kitchen and one bedroom.'
    the backend silently invented:
    '1 master bedroom with attached bathroom, 1 bedroom, 1 study room' for Floor 2.

    The new architecture MUST NEVER invent Floor 2 rooms!
    """
    brief = """
    Create a two-floor house on a 20 x 30 plot.
    Ground floor has living room, dining room, kitchen and one bedroom.
    """
    reqs = agent.parse(brief)
    assert reqs.target_floors == 2

    f1 = reqs.get_floor(1)
    f2 = reqs.get_floor(2)

    assert f1 is not None
    assert len(f1.room_requirements) >= 4

    # Floor 2 must exist as a shell, but have ZERO invented rooms!
    assert f2 is not None
    assert len(f2.room_requirements) == 0

    # Completeness check must block progression to planning
    pipeline_res = agent.process(brief)
    assert pipeline_res.can_proceed_to_planning is False
    assert pipeline_res.completeness.is_complete is False
    assert 2 in pipeline_res.completeness.missing_floors


def test_regression_bug5_no_automatic_default_room_injection(agent):
    """Old Bug 5: Minimal briefs like '20x30 plot, 1 floor, 1 study' must NOT

    inject default master bedroom, bathroom, kitchen, or living room.
    """
    brief = "20m x 30m plot, 1 floor, 1 study room"
    reqs = agent.parse(brief)
    f1 = reqs.get_floor(1)
    assert f1 is not None

    room_types = [r.room_type for r in f1.room_requirements]
    assert room_types == ["study"]
    assert "bedroom" not in room_types
    assert "master_bedroom" not in room_types
    assert "kitchen" not in room_types
    assert "bathroom" not in room_types
    assert "living" not in room_types
