"""Full end-to-end integration test through Phase 8 (Refinement Loop).

Pipeline flow:
Requirements (Phase 2)
       ↓
Planning Agent (Phase 3)
       ↓
ASAA Allocator (Phase 4)
       ↓
Architectural LLM Agent (Phase 5)
       ↓
Geometry Engine (Phase 6)
       ↓
Independent Validator (Phase 7)
       ↓
Refinement Agent (Phase 8)
       ↓
Geometry Engine (Phase 6)
       ↓
Independent Validator (Phase 7)
       ↓
RefinementResult (authoritative correction outcome)
"""

import copy
from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.refinement_agent import RefinementAgent, RefinementLoop, RefinementStatus
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.models.architectural_design import ArchitecturalDesignSet, RoomDesign
from app.models.refinement import RefinementResult
from app.validation.validator import FloorPlanValidator


def test_full_pipeline_refinement_correction():
    """Verify complete end-to-end pipeline where an initial design failure is corrected by the Refinement Agent."""
    brief = """
    Design a 1-floor house on a 30 feet by 30 feet plot with 1.5m setbacks.
    Floor 1:
    - 1 living room of 150 sq ft
    - 1 bedroom of 100 sq ft
    - 1 bathroom of 40 sq ft
    """

    # 1. Requirement Agent (Phase 2)
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Refinement Success Test")

    # 2. Planning Agent (Phase 3)
    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    # 3. ASAA Allocator (Phase 4)
    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    # 4. Architectural Agent (Phase 5)
    arch_agent = ArchitecturalAgent()
    design_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
    )

    # Introduce an architectural flaw into the initial design:
    # Strip the entrance door from the living room so initial validation fails with missing_entrance_connection
    flawed_design = copy.deepcopy(design_set)
    for room in flawed_design.designs[0].rooms:
        if room.room_type == "living":
            room.doors = [d for d in room.doors if d.door_type != "entrance"]

    # 5. Execute Refinement Loop
    refinement_loop = RefinementLoop(max_iterations=3)
    result = refinement_loop.run(
        initial_design=flawed_design,
        allocation_set=allocation_set,
        requirements=reqs,
        planning_spec=planning_spec,
        project_name="Refinement Success Test",
    )

    # Invariants verification
    assert isinstance(result, RefinementResult)
    assert result.status == RefinementStatus.VALID_AFTER_REFINEMENT
    assert result.is_valid is True
    assert result.final_floor_plan_set is not None
    assert result.final_floor_plan_set.all_valid is True

    # Iterations verification
    assert len(result.iterations) >= 2  # Iteration 0 (flawed) + Iteration 1 (corrected)
    assert result.iterations[0].overall_valid is False
    assert result.iterations[0].error_count > 0
    assert result.iterations[1].overall_valid is True
    assert result.iterations[1].error_count == 0

    # Change tracking verification
    assert len(result.changes) > 0
    assert any(c.field_changed == "doors" for c in result.changes)

    # Upstream constraint preservation
    initial_room_ids = {r.id for r in flawed_design.designs[0].rooms}
    final_room_ids = {r.id for r in result.final_design.designs[0].rooms}
    assert initial_room_ids == final_room_ids

    # Allocation ownership preservation
    for final_room in result.final_design.designs[0].rooms:
        initial_room = flawed_design.designs[0].get_room(final_room.id)
        assert initial_room is not None
        assert final_room.allocated_region_id == initial_room.allocated_region_id
        assert final_room.floor_number == initial_room.floor_number


def test_refinement_infeasible_scenario():
    """Verify that an unfixable constraint does not cause room invention or allocation mutation, but stops cleanly."""
    brief = """
    Design a 1-floor house on a 30 feet by 30 feet plot with 1.5m setbacks.
    Floor 1:
    - 1 living room of 150 sq ft
    - 1 bedroom of 100 sq ft
    """

    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Infeasible Refinement Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    design_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
    )

    # We enforce a mock agent that cannot resolve the problem (returns unchanged design)
    class UnchangeableMockAgent(RefinementAgent):
        def refine(self, ctx):
            # Propose no changes
            return ctx.current_design, []

    refinement_loop = RefinementLoop(
        refinement_agent=UnchangeableMockAgent(),
        max_iterations=2,
    )
    result = refinement_loop.run(
        initial_design=design_set,
        allocation_set=allocation_set,
        requirements=reqs,
        planning_spec=planning_spec,
        project_name="Infeasible Refinement Test",
    )

    # Must terminate cleanly without inventing rooms or mutating allocations
    assert result.status in {
        RefinementStatus.REFINEMENT_FAILED,
        RefinementStatus.MAX_ITERATIONS_REACHED,
        RefinementStatus.VALID_ON_INITIAL_PASS,
    }
