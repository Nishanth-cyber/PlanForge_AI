"""Phase 3 authoritative regression tests for Plot, Setback, and ASAA boundary preservation.

Tests strictly enforce:
1. Rectangular plot preservation (40x50, 30x40, 50x60 ft) across parser, planning, ASAA, geometry, and validation
2. Side setback preservation: side=1.5m preserves to left=1.5, right=1.5, side=1.5 in ASAA boundary
3. Four-direction setback preservation: front=2m, rear=3m, left=1.5m, right=1m all survive
4. L-shaped plot preservation: [(0,0), (40,0), (40,20), (25,20), (25,40), (0,40)] remains L-shaped and not converted to 40x40 box
5. Irregular polygon plot preservation: arbitrary polygon points remain unchanged
6. Room containment: room geometry is strictly contained inside the buildable boundary
7. Room dimensions do not replace plot dimensions ("Bedroom 12ft x 14ft" vs "Plot 40ft x 50ft")
8. Infeasible plot requirements report infeasibility instead of producing an invalid design
9. Spatial relationships and adjacency (Kitchen adjacent to Dining) are respected in allocation
10. Area-only plot behavior: deterministic 1.5:1 fallback when only area given; does not override explicit width/depth
"""

import pytest
from shapely.geometry import Polygon

from app.agents.requirement_agent.parser import RequirementParser
from app.agents.planning_agent.agent import PlanningAgent
from app.asaa.allocator import ASAAAllocator
from app.asaa.boundary import BuildableBoundaryCalculator
from app.asaa.exceptions import InfeasibleAllocationError, BoundaryConstraintError
from app.geometry.engine import GeometryEngine
from app.models.requirements import Requirements, RoomRequirement, FloorRequirement
from app.models.planning import PlanningSpec, FloorPlanSpec, RoomSpec
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.validation.validator import FloorPlanValidator


# =============================================================================
# Test 1 — Rectangular Plot Preservation
# =============================================================================

@pytest.mark.parametrize(
    "width_ft,depth_ft",
    [
        (40.0, 50.0),
        (30.0, 40.0),
        (50.0, 60.0),
    ],
)
def test_rectangular_plot_preservation_across_pipeline(width_ft: float, depth_ft: float):
    """Verify rectangular plot dimensions remain authoritative through the pipeline."""
    text = f"Single floor cottage. Plot size is {int(width_ft)}ft x {int(depth_ft)}ft with 2 bedrooms and living room."
    parser = RequirementParser()
    reqs = parser.parse(text)

    # 1. Parser / Requirements check
    expected_w = width_ft * 0.3048
    expected_d = depth_ft * 0.3048
    assert reqs.plot_dimensions is not None
    assert abs(reqs.plot_dimensions[0] - expected_w) < 1e-3
    assert abs(reqs.plot_dimensions[1] - expected_d) < 1e-3

    # 2. Planning Agent check
    planner = PlanningAgent()
    spec = planner.plan(reqs)
    assert spec.global_constraints.get("plot_dimensions") is not None
    pw, pd = spec.global_constraints["plot_dimensions"]
    assert abs(pw - expected_w) < 1e-3
    assert abs(pd - expected_d) < 1e-3

    # 3. ASAA Boundary check
    asaa = ASAAAllocator()
    buildable = asaa._derive_buildable_boundary(spec)
    b_xs = [p[0] for p in buildable.plot_polygon]
    b_ys = [p[1] for p in buildable.plot_polygon]
    assert abs((max(b_xs) - min(b_xs)) - expected_w) < 1e-3
    assert abs((max(b_ys) - min(b_ys)) - expected_d) < 1e-3

    # 4. Orchestration end-to-end check
    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(enable_refinement=False, enable_exports=False)
    result = orchestrator.generate(requirements=reqs, config=cfg)
    assert result.is_success is True
    fps = result.floor_plan_set
    assert fps is not None
    d_xs = [p[0] for p in fps.plot_boundary]
    d_ys = [p[1] for p in fps.plot_boundary]
    assert abs((max(d_xs) - min(d_xs)) - expected_w) < 1e-3
    assert abs((max(d_ys) - min(d_ys)) - expected_d) < 1e-3


# =============================================================================
# Test 2 — Side Setback Preservation
# =============================================================================

def test_side_setback_preservation():
    """Verify front=2m, rear=2m, side=1.5m preserves left=1.5, right=1.5, and side=1.5."""
    norm = BuildableBoundaryCalculator._normalize_setbacks({
        "front": 2.0,
        "rear": 2.0,
        "side": 1.5,
    })
    assert norm["front"] == 2.0
    assert norm["rear"] == 2.0
    assert norm["left"] == 1.5
    assert norm["right"] == 1.5
    assert norm["side"] == 1.5

    # Test through BuildableBoundaryCalculator.calculate
    plot = [(0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0)]
    buildable = BuildableBoundaryCalculator.calculate(
        plot_polygon=plot,
        setbacks={"front": 2.0, "rear": 2.0, "side": 1.5},
    )
    # Expected buildable: x from 1.5 to 18.5 (width 17.0), y from 2.0 to 28.0 (depth 26.0)
    xs = [p[0] for p in buildable.polygon]
    ys = [p[1] for p in buildable.polygon]
    assert abs(min(xs) - 1.5) < 1e-3
    assert abs(max(xs) - 18.5) < 1e-3
    assert abs(min(ys) - 2.0) < 1e-3
    assert abs(max(ys) - 28.0) < 1e-3


# =============================================================================
# Test 3 — Four-Direction Setbacks
# =============================================================================

def test_four_direction_setback_preservation():
    """Verify front=2m, rear=3m, left=1.5m, right=1m all survive independently."""
    setbacks = {
        "front": 2.0,
        "rear": 3.0,
        "left": 1.5,
        "right": 1.0,
    }
    norm = BuildableBoundaryCalculator._normalize_setbacks(setbacks)
    assert norm["front"] == 2.0
    assert norm["rear"] == 3.0
    assert norm["left"] == 1.5
    assert norm["right"] == 1.0

    plot = [(0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0)]
    buildable = BuildableBoundaryCalculator.calculate(
        plot_polygon=plot,
        setbacks=setbacks,
    )
    # front is min y (+2.0), rear is max y (-3.0) -> y in [2.0, 27.0]
    # left is min x (+1.5), right is max x (-1.0) -> x in [1.5, 19.0]
    xs = [p[0] for p in buildable.polygon]
    ys = [p[1] for p in buildable.polygon]
    assert abs(min(xs) - 1.5) < 1e-3
    assert abs(max(xs) - 19.0) < 1e-3
    assert abs(min(ys) - 2.0) < 1e-3
    assert abs(max(ys) - 27.0) < 1e-3


# =============================================================================
# Test 4 — L-Shaped Plot Preservation
# =============================================================================

def test_l_shaped_plot_preservation():
    """Verify an L-shaped plot remains polygonal and L-shaped, not a 40x40 box."""
    l_polygon = (
        (0.0, 0.0),
        (40.0, 0.0),
        (40.0, 20.0),
        (25.0, 20.0),
        (25.0, 40.0),
        (0.0, 40.0),
    )

    reqs = Requirements(
        project_name="L-Shaped Villa",
        target_floors=1,
        plot_shape=l_polygon,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=20.0),
                    RoomRequirement(room_type="bedroom", min_count=2, min_area_sqm=12.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=8.0),
                ],
            )
        ],
    )

    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(enable_refinement=False, enable_exports=False)
    result = orchestrator.generate(requirements=reqs, config=cfg)

    assert result.is_success is True
    fps = result.floor_plan_set
    assert fps is not None

    # Verify authoritative plot has 6 vertices matching original L-shape
    assert len(fps.plot_boundary) == 6
    for pt, orig in zip(fps.plot_boundary, l_polygon):
        assert abs(pt[0] - orig[0]) < 1e-3
        assert abs(pt[1] - orig[1]) < 1e-3

    # Verify buildable boundary is also L-shaped (has 6 vertices)
    assert len(fps.buildable_boundary) == 6

    # Verify no rooms fall in the cut-out corner (x > 25 and y > 20)
    cutout_poly = Polygon([(25.0, 20.0), (50.0, 20.0), (50.0, 50.0), (25.0, 50.0)])
    for room in fps.floor_plans[0].geometry.rooms:
        r_poly = Polygon(room.polygon)
        assert not r_poly.intersects(cutout_poly) or r_poly.intersection(cutout_poly).area < 1e-4, (
            f"Room {room.room_type} intersects cutout region!"
        )


# =============================================================================
# Test 5 — Irregular Plot Preservation
# =============================================================================

def test_irregular_plot_preservation():
    """Verify arbitrary polygon vertices remain unchanged."""
    irregular_polygon = (
        (0.0, 0.0),
        (35.0, 5.0),
        (30.0, 35.0),
        (5.0, 28.0),
    )

    reqs = Requirements(
        project_name="Trapezoidal Home",
        target_floors=1,
        plot_shape=irregular_polygon,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=18.0),
                    RoomRequirement(room_type="bedroom", min_count=1, min_area_sqm=12.0),
                ],
            )
        ],
    )

    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(enable_refinement=False, enable_exports=False)
    result = orchestrator.generate(requirements=reqs, config=cfg)

    assert result.is_success is True
    fps = result.floor_plan_set
    assert fps is not None
    assert len(fps.plot_boundary) == len(irregular_polygon)
    for pt, orig in zip(fps.plot_boundary, irregular_polygon):
        assert abs(pt[0] - orig[0]) < 1e-3
        assert abs(pt[1] - orig[1]) < 1e-3


# =============================================================================
# Test 6 — Room Containment within Buildable Boundary
# =============================================================================

def test_room_containment_in_buildable_boundary():
    """Verify all rooms are strictly contained inside buildable boundary."""
    reqs = Requirements(
        project_name="Containment Check",
        target_floors=1,
        plot_dimensions=(25.0, 30.0),
        setbacks={"front": 2.0, "rear": 2.0, "left": 1.5, "right": 1.5},
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=22.0),
                    RoomRequirement(room_type="bedroom", min_count=2, min_area_sqm=14.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=10.0),
                    RoomRequirement(room_type="bathroom", min_count=2, min_area_sqm=4.5),
                ],
            )
        ],
    )

    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(enable_refinement=False, enable_exports=False)
    result = orchestrator.generate(requirements=reqs, config=cfg)

    assert result.is_success is True
    fps = result.floor_plan_set
    assert fps is not None
    buildable_poly = Polygon(fps.buildable_boundary)

    for fp in fps.floor_plans:
        assert fp.geometry is not None
        for room in fp.geometry.rooms:
            room_poly = Polygon(room.polygon)
            # Check containment with small floating tolerance
            assert buildable_poly.buffer(1e-3).contains(room_poly), (
                f"Room {room.id} polygon not contained in buildable boundary!"
            )


# =============================================================================
# Test 7 — Room Dimensions Do Not Replace Plot Dimensions
# =============================================================================

def test_room_dimensions_do_not_replace_plot_dimensions():
    """Verify 'Bedroom 12ft x 14ft' does not become plot dimensions."""
    parser = RequirementParser()

    # Case A: Room dimensions alone -> plot_dimensions must be None
    reqs_a = parser.parse("Need a bedroom 12ft x 14ft and a kitchen 10ft x 10ft.")
    assert reqs_a.plot_dimensions is None

    # Case B: Explicit plot dimensions alongside room dimensions -> both distinct
    reqs_b = parser.parse("Plot size 40ft x 50ft. Bedroom 12ft x 14ft and kitchen 10ft x 10ft.")
    assert reqs_b.plot_dimensions is not None
    expected_w = 40.0 * 0.3048
    expected_d = 50.0 * 0.3048
    assert abs(reqs_b.plot_dimensions[0] - expected_w) < 1e-3
    assert abs(reqs_b.plot_dimensions[1] - expected_d) < 1e-3

    # Check the bedroom requirement has its own dimensions
    bed = next((r for r in reqs_b.all_room_requirements() if r.room_type == "bedroom"), None)
    assert bed is not None
    assert bed.user_dimensions is not None
    assert abs(bed.user_dimensions[0] - round(12.0 * 0.3048, 2)) < 1e-3
    assert abs(bed.user_dimensions[1] - round(14.0 * 0.3048, 2)) < 1e-3


# =============================================================================
# Test 8 — Infeasible Plot Reports Infeasibility
# =============================================================================

def test_infeasible_plot_reports_infeasibility():
    """Verify impossible requirements report infeasibility rather than an invalid design."""
    # 5m x 5m plot with 2m setbacks leaves 1m x 1m (1 sqm) buildable area,
    # but requests 5 large rooms totaling 100 sqm.
    reqs = Requirements(
        project_name="Impossible House",
        target_floors=1,
        plot_dimensions=(5.0, 5.0),
        setbacks={"front": 2.0, "rear": 2.0, "left": 2.0, "right": 2.0},
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=30.0),
                    RoomRequirement(room_type="bedroom", min_count=3, min_area_sqm=20.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=15.0),
                ],
            )
        ],
    )

    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(enable_refinement=False, enable_exports=False)
    result = orchestrator.generate(requirements=reqs, config=cfg)

    # Must NOT succeed with an invalid design
    assert result.is_success is False
    assert result.status == "failed"
    err = (result.error_message or "").lower()
    assert (
        "infeasible" in err
        or "budget" in err
        or "boundary" in err
        or "insufficient" in err
        or "exceeds" in err
        or "deficit" in err
    )


# =============================================================================
# Test 9 — Adjacency and Relationships
# =============================================================================

def test_adjacency_preservation():
    """Verify spatial relationships (e.g. Kitchen adjacent to Dining) are respected."""
    reqs = Requirements(
        project_name="Adjacent Villa",
        target_floors=1,
        plot_dimensions=(25.0, 25.0),
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=20.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=10.0, adjacency=["dining"]),
                    RoomRequirement(room_type="dining", min_count=1, min_area_sqm=12.0, adjacency=["kitchen"]),
                    RoomRequirement(room_type="bedroom", min_count=1, min_area_sqm=14.0),
                ],
            )
        ],
    )

    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(enable_refinement=False, enable_exports=False)
    result = orchestrator.generate(requirements=reqs, config=cfg)

    assert result.is_success is True
    fps = result.floor_plan_set
    assert fps is not None

    rooms = fps.floor_plans[0].geometry.rooms
    kitchen = next((r for r in rooms if r.room_type == "kitchen"), None)
    dining = next((r for r in rooms if r.room_type == "dining"), None)
    assert kitchen is not None
    assert dining is not None

    k_poly = Polygon(kitchen.polygon)
    d_poly = Polygon(dining.polygon)
    # Check that they touch or are close (within corridor / wall distance)
    dist = k_poly.distance(d_poly)
    assert dist <= 2.5, f"Kitchen and dining too far apart: {dist}m"


# =============================================================================
# Test 10 — Area-Only Plot Fallback
# =============================================================================

def test_area_only_plot_fallback():
    """Verify area-only input produces deterministic 1.5:1 rectangle without overwriting explicit dimensions."""
    parser = RequirementParser()
    reqs = parser.parse("Single storey house. The plot area is 2400 sq ft with 2 bedrooms.")

    # plot_dimensions must be None in Requirements
    assert reqs.plot_dimensions is None
    expected_sqm = 2400.0 * 0.092903
    assert reqs.plot_area_sqm is not None
    assert abs(reqs.plot_area_sqm - expected_sqm) < 1.0

    # PlanningAgent preserves plot_area_sqm in global constraints
    planner = PlanningAgent()
    spec = planner.plan(reqs)
    assert spec.global_constraints.get("plot_area_sqm") is not None
    assert abs(spec.global_constraints["plot_area_sqm"] - expected_sqm) < 1.0

    # ASAA derives 1.5:1 rectangle from area deterministically
    asaa = ASAAAllocator()
    buildable = asaa._derive_buildable_boundary(spec)
    poly = buildable.plot_polygon
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    w = max(xs) - min(xs)
    d = max(ys) - min(ys)
    # 1.5:1 aspect ratio check
    ratio = max(w, d) / min(w, d)
    assert abs(ratio - 1.5) < 1e-2
    # Area should match expected plot area
    assert abs((w * d) - expected_sqm) < 1.0
