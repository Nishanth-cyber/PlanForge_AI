"""Full pipeline integration test through Phase 6 (Geometry Engine).

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
FloorPlanSet
"""

from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.models.floor_plan import FloorPlanSet


def test_full_pipeline_through_geometry():
    """Verify complete pipeline execution from raw text requirements through physical geometry."""
    brief = """
    Design a 2-floor house on a 30 feet by 40 feet plot with 2m setbacks.
    Floor 1:
    - 1 large living room of 200 sq ft next to dining
    - 1 dining room of 120 sq ft next to kitchen
    - 1 kitchen of 100 sq ft
    - 1 guest bedroom of 120 sq ft
    - 1 common bathroom of 45 sq ft
    - staircase to upper floor
    Floor 2:
    - 1 master bedroom of 180 sq ft with attached bathroom of 50 sq ft
    - 1 bedroom of 120 sq ft
    - 1 study room of 90 sq ft
    - 1 common bathroom of 45 sq ft
    """

    # 1. Requirement Agent (Phase 2)
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Villa Serena")
    assert reqs.target_floors == 2
    assert len(reqs.floors) == 2

    # 2. Planning Agent (Phase 3)
    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)
    assert len(planning_spec.floors) == 2

    # 3. ASAA Allocator (Phase 4)
    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)
    assert len(allocation_set.allocations) == 2
    assert allocation_set.staircase_aligned is True

    # 4. Architectural Agent (Phase 5 - Mock LLM)
    arch_agent = ArchitecturalAgent()
    design_set = arch_agent.design(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
    )
    assert len(design_set.designs) == 2

    # 5. Geometry Engine (Phase 6)
    geo_engine = GeometryEngine()
    floor_plan_set = geo_engine.construct(
        design_set=design_set,
        allocation_set=allocation_set,
        project_name="Villa Serena",
    )

    # Verification on FloorPlanSet
    assert isinstance(floor_plan_set, FloorPlanSet)
    assert floor_plan_set.project_name == "Villa Serena"
    assert len(floor_plan_set.floor_plans) == 2

    # Verification of Floor 1 Geometry
    fp1 = floor_plan_set.get_floor_plan(1)
    assert fp1 is not None
    assert fp1.floor_number == 1
    assert fp1.is_valid is False  # Phase 7 responsibility
    assert fp1.validation is None

    geom1 = fp1.geometry
    assert geom1 is not None
    f1_room_types = {r.room_type for r in geom1.rooms if not r.is_corridor}
    assert "living" in f1_room_types
    assert "dining" in f1_room_types
    assert "kitchen" in f1_room_types
    assert "bedroom" in f1_room_types or "guest_bedroom" in f1_room_types
    assert "bathroom" in f1_room_types

    # Verification of Floor 2 Geometry
    fp2 = floor_plan_set.get_floor_plan(2)
    assert fp2 is not None
    assert fp2.floor_number == 2
    assert fp2.is_valid is False
    assert fp2.validation is None

    geom2 = fp2.geometry
    assert geom2 is not None
    f2_room_types = {r.room_type for r in geom2.rooms if not r.is_corridor}
    assert "master_bedroom" in f2_room_types
    assert "bedroom" in f2_room_types
    assert "study" in f2_room_types or "study_room" in f2_room_types
    assert "bathroom" in f2_room_types

    # Verify physical elements exist on both floors
    for fp in [fp1, fp2]:
        geom = fp.geometry
        # Walls exist
        assert len(geom.walls) >= 4
        for w in geom.walls:
            assert len(w.polygon) == 4
            assert w.thickness > 0
            assert len(w.room_ids) >= 1

        # Doors exist
        assert len(geom.doors) >= 1
        for d in geom.doors:
            assert d.width > 0
            assert d.height > 0
            assert d.wall_id != ""

        # Windows exist
        assert len(geom.windows) >= 1
        for win in geom.windows:
            assert win.width > 0
            assert win.height > 0
            assert win.wall_id != ""

        # Staircases exist on both floors and are vertically aligned
        assert len(geom.staircases) == 1
        stair = geom.staircases[0]
        assert stair.riser_count == 16
        assert stair.tread_depth == 0.28

    # Verify vertical alignment of staircases across floors
    stair1 = fp1.geometry.staircases[0]
    stair2 = fp2.geometry.staircases[0]
    assert stair1.polygon == stair2.polygon

    # Verify rooms have dual polygons with positive area
    for fp in [fp1, fp2]:
        for r in fp.geometry.rooms:
            assert len(r.built_polygon) >= 3
            assert len(r.usable_polygon) >= 3
            assert r.area_sqm > 0
            assert r.floor_number == fp.floor_number

    # Verify total usable area across floors
    assert floor_plan_set.total_usable_area > 0
