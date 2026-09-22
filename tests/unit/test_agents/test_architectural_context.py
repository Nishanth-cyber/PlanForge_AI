"""Unit tests for ArchitecturalContext and ContextBuilder."""

from app.agents.architectural_agent.context import ContextBuilder
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement


def test_context_builder_basic_mapping():
    """Test ContextBuilder maps PlanningSpec and AllocationSet into immutable context."""
    r_living = RoomSpec(
        id="rs_living_1",
        room_type="living",
        floor_number=1,
        target_area_sqm=30.0,
        min_area_sqm=25.0,
        priority="high",
        room_category="social",
    )
    f_spec = FloorPlanSpec(
        floor_number=1,
        floor_name="Ground Floor",
        room_specs=[r_living],
        circulation_zones=["public_circulation"],
        circulation_notes="Central foyer entry",
        entrance_intent={"facing": "north", "preferred_room": "living"},
    )
    p_spec = PlanningSpec(
        project_name="Villa Serena",
        floors=[f_spec],
        global_constraints={"orientation": "north"},
    )

    reg_living = AllocatedRegion(
        id="reg_living_1",
        room_type="living",
        room_spec_id="rs_living_1",
        floor_number=1,
        target_area_sqm=30.0,
        area_sqm=29.5,
        approximate_dimensions=(5.0, 6.0),
        polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 6.0), (0.0, 6.0)],
        centroid=(2.5, 3.0),
        priority="high",
        adjacency_regions=["reg_foyer_1"],
    )
    alloc = Allocation(
        floor_number=1,
        allocated_regions=[reg_living],
    )
    alloc_set = AllocationSet(allocations=[alloc])

    ctx = ContextBuilder.build(p_spec, alloc_set)
    assert ctx.project_name == "Villa Serena"
    assert len(ctx.floors) == 1

    f_ctx = ctx.get_floor_context(1)
    assert f_ctx is not None
    assert f_ctx.floor_name == "Ground Floor"
    assert len(f_ctx.rooms) == 1

    r_ctx = f_ctx.get_room_context("rs_living_1")
    assert r_ctx is not None
    assert r_ctx.room_type == "living"
    assert r_ctx.allocated_region_id == "reg_living_1"
    assert r_ctx.allocated_area_sqm == 29.5
    assert r_ctx.approximate_dimensions == (5.0, 6.0)
    assert r_ctx.priority == "high"


def test_context_builder_preserves_user_vs_system_provenance():
    """Test that ContextBuilder preserves user-required vs system-preferred relationship distinctions."""
    r_living = RoomSpec(id="rs_liv", room_type="living", floor_number=1)
    r_dining = RoomSpec(id="rs_din", room_type="dining", floor_number=1)
    r_kitchen = RoomSpec(id="rs_kit", room_type="kitchen", floor_number=1)

    f_spec = FloorPlanSpec(
        floor_number=1,
        room_specs=[r_living, r_dining, r_kitchen],
        # System adjacency graph contains living<->dining and dining<->kitchen
        adjacency_matrix={
            "living": ["dining"],
            "dining": ["living", "kitchen"],
            "kitchen": ["dining"],
        },
    )
    p_spec = PlanningSpec(floors=[f_spec])

    # User explicitly requested living <-> dining, but NOT dining <-> kitchen
    req_living = RoomRequirement(room_type="living", adjacency={"dining"})
    req_dining = RoomRequirement(room_type="dining", adjacency={"living"})
    req_kitchen = RoomRequirement(room_type="kitchen", adjacency=set())
    reqs = Requirements(floors=[FloorRequirement(floor_number=1, room_requirements=[req_living, req_dining, req_kitchen])])

    reg_liv = AllocatedRegion(id="reg_liv", room_type="living", room_spec_id="rs_liv")
    reg_din = AllocatedRegion(id="reg_din", room_type="dining", room_spec_id="rs_din")
    reg_kit = AllocatedRegion(id="reg_kit", room_type="kitchen", room_spec_id="rs_kit")
    alloc_set = AllocationSet(allocations=[Allocation(floor_number=1, allocated_regions=[reg_liv, reg_din, reg_kit])])

    ctx = ContextBuilder.build(p_spec, alloc_set, requirements=reqs)
    f_ctx = ctx.get_floor_context(1)
    din_ctx = f_ctx.get_room_context("rs_din")

    assert din_ctx is not None
    # User requested: living
    assert "living" in din_ctx.user_required_adjacencies
    # System derived: kitchen
    assert "kitchen" in din_ctx.system_preferred_adjacencies
