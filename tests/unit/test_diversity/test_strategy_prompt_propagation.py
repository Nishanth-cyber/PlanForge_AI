"""Unit tests for strategy assignment and prompt/context propagation."""

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.architectural_agent.context import ContextBuilder, FloorDesignContext
from app.agents.architectural_agent.prompts import build_floor_prompt
from app.llm.client import MockLLMClient
from app.models.allocation import Allocation, AllocationSet, AllocatedRegion
from app.models.alternatives import DesignStrategy
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_strategy_propagation_into_prompt_and_context():
    """Verify that specifying a strategy passes it into context and builds it into the prompt."""
    reg = AllocatedRegion(id="reg_liv", room_type="living", approximate_dimensions=(4.0, 5.0), area_sqm=20.0)
    alloc = Allocation(floor_number=1, allocated_regions=[reg])
    alloc_set = AllocationSet(allocations=[alloc])

    rs = RoomSpec(id="r_liv", room_type="living", floor_number=1, target_area_sqm=20.0)
    plan_spec = PlanningSpec(floors=[FloorPlanSpec(floor_number=1, room_specs=[rs])])

    # 1. Build context with strategy
    context = ContextBuilder.build(
        planning_spec=plan_spec,
        allocation_set=alloc_set,
        strategy=DesignStrategy.CORRIDOR_CENTRIC.value,
        alternative_index=2,
    )

    f_ctx = context.get_floor_context(1)
    assert f_ctx is not None
    assert f_ctx.strategy == "corridor_centric"
    assert f_ctx.alternative_index == 2

    # 2. Build prompt
    prompt = build_floor_prompt(f_ctx)
    assert "Design Strategy: corridor_centric" in prompt
    assert "Alternative Index: 2" in prompt
    assert "corridor_centric" in prompt


def test_deterministic_mock_generates_strategy_specific_output():
    """Verify that MockLLMClient produces different layouts when strategy is varied."""
    reg1 = AllocatedRegion(id="reg_1", room_type="living", approximate_dimensions=(4.0, 5.0), area_sqm=20.0, adjacency_regions=["reg_2"])
    reg2 = AllocatedRegion(id="reg_2", room_type="dining", approximate_dimensions=(3.0, 4.0), area_sqm=12.0, adjacency_regions=["reg_1"])
    alloc = Allocation(floor_number=1, allocated_regions=[reg1, reg2])
    alloc_set = AllocationSet(allocations=[alloc])

    rs1 = RoomSpec(id="r1", room_type="living", floor_number=1)
    rs2 = RoomSpec(id="r2", room_type="dining", floor_number=1)
    plan_spec = PlanningSpec(floors=[FloorPlanSpec(floor_number=1, room_specs=[rs1, rs2])])

    agent = ArchitecturalAgent()

    # Generate design with social_centric
    d_social = agent.design(plan_spec, alloc_set, strategy="social_centric")
    liv_social = d_social.get_design(1).rooms[0]
    social_doors = [d.connects_to for d in liv_social.doors]
    assert "dining" in social_doors

    # Generate design with corridor_centric
    d_corridor = agent.design(plan_spec, alloc_set, strategy="corridor_centric")
    liv_corridor = d_corridor.get_design(1).rooms[0]
    corridor_doors = [d.connects_to for d in liv_corridor.doors]
    assert "circulation" in corridor_doors
