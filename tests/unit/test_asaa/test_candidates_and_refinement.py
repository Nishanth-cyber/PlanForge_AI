"""Unit tests for ASAA candidate generation, scoring, and adaptive refinement."""

from shapely.geometry import Polygon
from app.asaa.allocator import ASAAAllocator
from app.asaa.candidate_generator import CandidateGenerator
from app.asaa.refiner import AdaptiveRefiner
from app.asaa.scoring import CandidateScorer
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_multiple_candidates_generated():
    """Test generating multiple diverse candidates with distinct strategies."""
    buildable = Polygon([(0.0, 0.0), (15.0, 0.0), (15.0, 15.0), (0.0, 15.0)])
    rooms = [
        RoomSpec(room_type="living", target_area_sqm=30.0, room_category="social"),
        RoomSpec(room_type="dining", target_area_sqm=15.0, room_category="social"),
        RoomSpec(room_type="kitchen", target_area_sqm=15.0, room_category="service"),
        RoomSpec(room_type="bedroom", target_area_sqm=20.0, room_category="private"),
    ]
    budgets = {r.id: r.target_area_sqm for r in rooms}

    candidates = CandidateGenerator.generate_candidates(
        buildable_polygon=buildable,
        room_specs=rooms,
        room_budgets=budgets,
        num_candidates=3,
        seed=42,
    )
    assert len(candidates) == 3
    strategies = {c.strategy for c in candidates}
    assert len(strategies) == 3


def test_candidate_scoring_breakdown():
    """Test that candidate scoring produces an explainable metric breakdown."""
    buildable = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 12.0), (0.0, 12.0)])
    rooms = [
        RoomSpec(room_type="living", target_area_sqm=30.0, priority="high"),
        RoomSpec(room_type="kitchen", target_area_sqm=15.0, priority="normal"),
    ]
    budgets = {r.id: r.target_area_sqm for r in rooms}

    cands = CandidateGenerator.generate_candidates(
        buildable_polygon=buildable,
        room_specs=rooms,
        room_budgets=budgets,
        num_candidates=1,
    )
    is_valid, score, breakdown, _ = CandidateScorer.evaluate(
        items=cands[0].items,
        buildable_polygon=buildable,
        room_specs=rooms,
    )
    assert is_valid is True
    assert score > 0.0
    assert "area_suitability" in breakdown
    assert "relationship_satisfaction" in breakdown
    assert "shape_compactness" in breakdown
    assert "circulation_connectivity" in breakdown
    assert "orientation_preference" in breakdown
    assert "priority_satisfaction" in breakdown


def test_adaptive_refinement_improves_or_maintains_score():
    """Test that adaptive refinement improves or maintains candidate score without violating constraints."""
    buildable = Polygon([(0.0, 0.0), (12.0, 0.0), (12.0, 12.0), (0.0, 12.0)])
    rooms = [
        RoomSpec(room_type="living", target_area_sqm=30.0),
        RoomSpec(room_type="bedroom", target_area_sqm=20.0),
        RoomSpec(room_type="dining", target_area_sqm=15.0),
    ]
    budgets = {r.id: r.target_area_sqm for r in rooms}

    cands = CandidateGenerator.generate_candidates(
        buildable_polygon=buildable,
        room_specs=rooms,
        room_budgets=budgets,
        num_candidates=1,
    )
    cand = cands[0]
    initial_score = cand.score

    refined = AdaptiveRefiner.refine(
        candidate=cand,
        buildable_polygon=buildable,
        room_specs=rooms,
        max_iterations=5,
    )
    assert refined.score >= initial_score
    assert refined.is_valid is True


def test_determinism_with_seed():
    """Test that identical PlanningSpec and seed produce identical allocation results."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=30.0),
                    RoomSpec(room_type="dining", target_area_sqm=15.0),
                ],
            )
        ],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 12.0},
    )

    allocator_1 = ASAAAllocator(seed=12345)
    allocator_2 = ASAAAllocator(seed=12345)

    res_1 = allocator_1.allocate(spec)
    res_2 = allocator_2.allocate(spec)

    r1_polys = [r.polygon for r in res_1.get_allocation(1).allocated_regions]
    r2_polys = [r.polygon for r in res_2.get_allocation(1).allocated_regions]
    assert r1_polys == r2_polys
