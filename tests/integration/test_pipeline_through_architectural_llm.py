"""Integration test for the full pipeline through the Architectural LLM stage.

Pipeline flow:
Requirement Agent (Phase 2)
      ↓
Planning Agent (Phase 3)
      ↓
PlanningSpec
      ↓
ASAA Allocator (Phase 4)
      ↓
AllocationSet
      ↓
Architectural Agent (Phase 5)
      ↓
ArchitecturalDesignSet
"""

from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.models.architectural_design import ArchitecturalDesignSet


def test_full_pipeline_through_architectural_llm():
    """Verify complete pipeline execution on a realistic 2-floor villa."""
    brief = """
    Design a 2-floor house on a 30 feet by 40 feet plot with 2m setbacks all around.
    Floor 1:
    - 1 large living room of 250 sq ft next to dining
    - 1 dining room of 150 sq ft next to kitchen
    - 1 kitchen of 120 sq ft
    - 1 powder room of 40 sq ft
    - staircase to upper floor
    Floor 2:
    - 1 master bedroom of 220 sq ft with attached bathroom of 60 sq ft
    - 1 guest bedroom of 130 sq ft
    - 1 common bathroom of 50 sq ft
    """

    # Stage 1: Requirement Agent
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Suncrest Villa")
    assert reqs.target_floors == 2
    assert len(reqs.floors) == 2

    # Stage 2: Planning Agent
    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)
    assert len(planning_spec.floors) == 2

    # Stage 3: ASAA Allocator
    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)
    assert len(allocation_set.allocations) == 2
    assert allocation_set.staircase_aligned is True

    # Stage 4: Architectural Agent (Mock LLM)
    arch_agent = ArchitecturalAgent()
    design_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
    )

    # Assertions on ArchitecturalDesignSet
    assert isinstance(design_set, ArchitecturalDesignSet)
    assert design_set.allocation_set_id == allocation_set.id
    assert len(design_set.designs) == 2

    # Check Floor 1 Design
    d1 = design_set.get_design(1)
    assert d1 is not None
    assert d1.floor_number == 1
    assert d1.staircase_intent is not None
    assert d1.allocation_id is not None
    f1_room_types = {r.room_type for r in d1.rooms}
    assert "living" in f1_room_types
    assert "dining" in f1_room_types
    assert "kitchen" in f1_room_types

    # Check Floor 2 Design
    d2 = design_set.get_design(2)
    assert d2 is not None
    assert d2.floor_number == 2
    assert d2.staircase_intent is not None
    f2_room_types = {r.room_type for r in d2.rooms}
    assert "master_bedroom" in f2_room_types
    assert "bedroom" in f2_room_types
    assert "bathroom" in f2_room_types

    # Traceability: Every room design references a valid ASAA allocated region
    alloc_1 = allocation_set.get_allocation(1)
    alloc_1_reg_ids = {r.id for r in alloc_1.allocated_regions}
    for r in d1.rooms:
        assert r.allocated_region_id in alloc_1_reg_ids
        assert len(r.doors) >= 1
        assert len(r.windows) >= 1

    alloc_2 = allocation_set.get_allocation(2)
    alloc_2_reg_ids = {r.id for r in alloc_2.allocated_regions}
    for r in d2.rooms:
        assert r.allocated_region_id in alloc_2_reg_ids

    # Stage boundary check: Zero geometry objects generated
    for d in design_set.designs:
        for r in d.rooms:
            assert not hasattr(r, "walls")
            assert not hasattr(r, "wall_thickness")
            for door in r.doors:
                assert not hasattr(door, "swing_arc_polygon")
            for win in r.windows:
                assert not hasattr(win, "opening_polygon")
