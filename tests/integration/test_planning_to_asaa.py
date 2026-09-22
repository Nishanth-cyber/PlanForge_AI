"""Integration tests for the Planning-to-ASAA pipeline.

Verifies end-to-end transformation:
Requirements (Phase 2)
      ↓
Planning Agent (Phase 3)
      ↓
PlanningSpec
      ↓
ASAA Allocator (Phase 4)
      ↓
AllocationSet
"""

from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.models.allocation import AllocationSet


def test_end_to_end_requirement_planning_to_asaa_villa():
    """Test full pipeline on a 2-story villa with attached bathroom and kitchen-dining connection."""
    brief = """
    I want a 2-floor villa on a 15m by 20m plot with 2m setbacks all around.
    Floor 1:
    - 1 large living room of 30 sqm
    - 1 dining room of 15 sqm connected to living room
    - 1 kitchen of 15 sqm
    - 1 powder room of 4 sqm
    - staircase to upper floor
    Floor 2:
    - 1 master bedroom of 25 sqm with attached bathroom of 6 sqm
    - 1 guest bedroom of 18 sqm
    - 1 common bathroom of 5 sqm
    """

    # Stage 1: Requirement Agent
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief)
    assert reqs.target_floors == 2
    assert len(reqs.floors) == 2

    # Stage 2: Planning Agent
    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)
    assert len(planning_spec.floors) == 2

    # Stage 3: ASAA Allocator
    asaa = ASAAAllocator(seed=42)
    alloc_set = asaa.allocate(planning_spec)

    assert isinstance(alloc_set, AllocationSet)
    assert len(alloc_set.allocations) == 2
    assert alloc_set.staircase_aligned is True

    # Check Floor 1
    alloc_f1 = alloc_set.get_allocation(1)
    assert alloc_f1 is not None
    assert alloc_f1.total_area_sqm > 0
    assert alloc_f1.get_staircase_region() is not None
    assert len(alloc_f1.get_regions_by_type("living")) == 1
    assert len(alloc_f1.get_regions_by_type("dining")) == 1

    # Check Floor 2
    alloc_f2 = alloc_set.get_allocation(2)
    assert alloc_f2 is not None
    assert alloc_f2.total_area_sqm > 0
    assert alloc_f2.get_staircase_region() is not None
    assert len(alloc_f2.get_regions_by_type("master_bedroom")) == 1
    assert len(alloc_f2.get_regions_by_type("bathroom")) >= 1

    # Check staircase alignment
    stair_1 = alloc_f1.get_staircase_region()
    stair_2 = alloc_f2.get_staircase_region()
    assert stair_1.polygon == stair_2.polygon
