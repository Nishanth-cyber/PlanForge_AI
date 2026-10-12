"""Generalization & Stress Test Fixtures for PlanForge Phase 9 Evaluation.

Provides:
1. Held-Out Plot Geometries (strictly not tuned against, evaluating out-of-distribution performance):
   - Rectangular plots with extreme proportions (narrow and elongated)
   - L-shaped non-convex plots with asymmetric wings
   - T-shaped non-convex plots with junction bottlenecks
   - Irregular polygonal boundaries (pentagonal)
   - Tight setback envelopes near feasibility limits
   - Multi-wing bifurcation plots
   - Irregular multi-floor configurations
2. Complexity & Constraint Stress Fixtures (varying one stress factor at a time):
   - High room count (12 rooms)
   - Dense room area packing (tight envelope)
   - Mathematically infeasible room-area demand
   - Directly conflicting functional adjacencies
   - Extreme room aspect ratios
   - Multi-floor programs with vertical circulation stress
   - Ambiguous / incomplete requirements
   - Explicitly unsupported curved plot boundary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FixtureCategory(str, Enum):
    HELDOUT_GEOMETRY = "heldout_geometry"
    COMPLEXITY_STRESS = "complexity_stress"
    FEASIBILITY_LIMIT = "feasibility_limit"
    CONFLICTING_CONSTRAINTS = "conflicting_constraints"
    UNSUPPORTED_INPUT = "unsupported_input"


class FeasibilityExpectation(str, Enum):
    FEASIBLE = "feasible"
    FEASIBLE_BUT_DIFFICULT = "feasible_but_difficult"
    INFEASIBLE = "infeasible"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    UNSUPPORTED_INPUT = "unsupported_input"


@dataclass
class RobustnessFixture:
    """A benchmark fixture specifically designed for generalization or stress testing."""

    fixture_id: str
    name: str
    description: str
    category: FixtureCategory
    expected_feasibility: FeasibilityExpectation
    brief: str
    geometric_properties: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "expected_feasibility": self.expected_feasibility.value,
            "brief": self.brief,
            "geometric_properties": self.geometric_properties,
            "limitations": self.limitations,
            "seed": self.seed,
        }


# ============================================================================
# 1. HELD-OUT GEOMETRY FIXTURES (Held-out from algorithm parameter tuning)
# ============================================================================

HELDOUT_GEOMETRY_FIXTURES: List[RobustnessFixture] = [
    RobustnessFixture(
        fixture_id="heldout_01_narrow_elongated",
        name="Narrow Elongated Plot (1:4 Aspect Ratio)",
        description="Extreme 20ft by 80ft plot challenging linear corridor arrangement and single-file room packing.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "plot_shape": "rectangular",
            "aspect_ratio": 4.0,
            "width_m": 6.1,
            "length_m": 24.4,
            "buildable_width_m": 4.1,
            "buildable_length_m": 20.4,
        },
        limitations=["Rooms must be sequenced linearly due to narrow 4.1m buildable width"],
        brief="""
        Single floor residence on a 20 feet by 80 feet plot with front setback: 2m, rear setback: 2m, side setback: 1m.
        Floor 1:
        - 1 living room of 180 sq ft
        - 1 dining room of 110 sq ft
        - 1 kitchen of 90 sq ft
        - 1 bedroom of 130 sq ft
        - 1 bathroom of 45 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="heldout_02_nonconvex_l_wings",
        name="Asymmetric L-Shaped Winged Plot",
        description="Non-convex L-shaped boundary with unequal wing proportions, testing corner circulation and boundary containment.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE,
        geometric_properties={
            "plot_shape": "l-shaped",
            "non_convex": True,
            "wing_proportions": [0.6, 0.4],
        },
        limitations=["Requires multi-zone decomposition around the interior reflex angle"],
        brief="""
        Single floor modern residence on an L-shaped plot within a 45 feet by 55 feet bounding box with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 220 sq ft
        - 1 dining room of 130 sq ft
        - 1 kitchen of 120 sq ft
        - 2 bedrooms of 140 sq ft each
        - 1 bathroom of 55 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="heldout_03_nonconvex_t_junction",
        name="T-Shaped Junction Plot",
        description="Non-convex T-shaped plot with stem-to-crossbar circulation bottleneck.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "plot_shape": "t-shaped",
            "non_convex": True,
            "bottleneck_width_m": 5.0,
        },
        limitations=["Access between stem and wings requires central junction corridor"],
        brief="""
        Single floor family home on a 50 feet by 50 feet T-shaped plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 210 sq ft
        - 1 dining room of 120 sq ft
        - 1 kitchen of 110 sq ft
        - 2 bedrooms of 130 sq ft each
        - 1 bathroom of 50 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="heldout_04_irregular_pentagon",
        name="Irregular Pentagonal Boundary",
        description="Non-orthogonal 5-sided convex boundary testing non-rectilinear boundary clipping.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "plot_shape": "irregular_pentagon",
            "num_vertices": 5,
            "non_orthogonal": True,
        },
        limitations=["Non-orthogonal boundary edges require polygonal perimeter clipping"],
        brief="""
        Single floor home on a 45 feet by 50 feet irregular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 200 sq ft
        - 1 kitchen of 110 sq ft
        - 2 bedrooms of 130 sq ft each
        - 1 bathroom of 50 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="heldout_05_tight_setback_envelope",
        name="Deep Setback Constrained Envelope",
        description="Deep setbacks (3m front/rear, 2.5m sides) creating a narrow 5m buildable strip on a standard suburban plot.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE,
        geometric_properties={
            "plot_shape": "rectangular",
            "front_setback_m": 3.0,
            "rear_setback_m": 3.0,
            "side_setback_m": 2.5,
            "buildable_width_m": 5.2,
        },
        limitations=["Very high setback-to-plot ratio (setbacks consume 52% of total plot area)"],
        brief="""
        Single floor bungalow on a 35 feet by 50 feet plot with front setback: 3m, rear setback: 3m, side setback: 2.5m.
        Floor 1:
        - 1 living room of 180 sq ft
        - 1 dining room of 100 sq ft
        - 1 kitchen of 90 sq ft
        - 1 bedroom of 120 sq ft
        - 1 bathroom of 45 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="heldout_06_narrow_wing_bifurcation",
        name="Dual-Wing Narrow Bifurcation Plot",
        description="Plot with two parallel wings connected by a narrow circulation bridge.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "plot_shape": "dual_wing",
            "bridge_width_m": 3.5,
        },
        limitations=["Strict zoning separation required between social and private wings across bridge"],
        brief="""
        Single floor courtyard residence on a 45 feet by 45 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 190 sq ft
        - 1 dining room of 110 sq ft
        - 1 kitchen of 100 sq ft
        - 2 bedrooms of 120 sq ft each
        - 1 bathroom of 50 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="heldout_07_irregular_multifloor",
        name="Two-Floor Irregular Plot Residence",
        description="Two-floor program on an irregular L-shaped footprint with vertical circulation alignment.",
        category=FixtureCategory.HELDOUT_GEOMETRY,
        expected_feasibility=FeasibilityExpectation.FEASIBLE,
        geometric_properties={
            "plot_shape": "l-shaped",
            "floors": 2,
            "requires_staircase": True,
        },
        limitations=["Staircase core must vertically align between Floor 1 and Floor 2"],
        brief="""
        Two floor residence on a 40 feet by 50 feet L-shaped plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 200 sq ft
        - 1 dining room of 120 sq ft
        - 1 kitchen of 110 sq ft
        Floor 2:
        - 2 bedrooms of 140 sq ft each
        - 1 bathroom of 50 sq ft
        """,
    ),
]


# ============================================================================
# 2. CONSTRAINT & COMPLEXITY STRESS FIXTURES
# ============================================================================

COMPLEXITY_STRESS_FIXTURES: List[RobustnessFixture] = [
    RobustnessFixture(
        fixture_id="stress_01_high_room_count",
        name="12-Room High-Complexity Program",
        description="High room count program (12 rooms) testing ASAA partition scalability and connectivity graph scaling.",
        category=FixtureCategory.COMPLEXITY_STRESS,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "room_count": 12,
            "plot_dimensions": "60ft x 80ft",
        },
        limitations=["High graph node count requires robust multi-branch corridor routing"],
        brief="""
        Single floor luxury villa on a 60 feet by 80 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 300 sq ft
        - 1 dining room of 160 sq ft
        - 1 kitchen of 150 sq ft
        - 4 bedrooms of 140 sq ft each
        - 3 bathrooms of 50 sq ft each
        - 1 study of 100 sq ft
        - 1 utility room of 60 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_02_dense_area_demand",
        name="Dense 92% Buildable Envelope Packing",
        description="Requested room areas occupy 92% of buildable envelope, testing minimal-waste space packing.",
        category=FixtureCategory.COMPLEXITY_STRESS,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "buildable_area_utilization": 0.92,
        },
        limitations=["Very narrow circulation margins remaining after room allocation"],
        brief="""
        Single floor compact villa on a 35 feet by 45 feet plot with front setback: 1.5m, rear setback: 1.5m, side setback: 1.5m.
        Floor 1:
        - 1 living room of 220 sq ft
        - 1 dining room of 130 sq ft
        - 1 kitchen of 120 sq ft
        - 2 bedrooms of 140 sq ft each
        - 1 bathroom of 55 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_03_infeasible_area_overload",
        name="Deterministic Infeasible Area Overload (150%)",
        description="Room area demands exceed total buildable envelope by 50%, verifying deterministic infeasibility detection without false valid designs.",
        category=FixtureCategory.FEASIBILITY_LIMIT,
        expected_feasibility=FeasibilityExpectation.INFEASIBLE,
        geometric_properties={
            "area_demand_ratio": 1.50,
            "ground_truth_feasible": False,
        },
        limitations=["Physically impossible to fit inside envelope"],
        brief="""
        Single floor home on a 25 feet by 30 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 400 sq ft
        - 1 dining room of 250 sq ft
        - 1 kitchen of 200 sq ft
        - 2 bedrooms of 200 sq ft each
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_04_conflicting_adjacencies",
        name="Directly Conflicting Adjacency & Separation",
        description="Kitchen is requested to be directly adjacent to bedroom while also strictly acoustically isolated from private zone.",
        category=FixtureCategory.CONFLICTING_CONSTRAINTS,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "contradictory_rules": True,
        },
        limitations=["Constraint priority resolution must favor mandatory building code separation over soft preference"],
        brief="""
        Single floor house on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 200 sq ft
        - 1 dining room of 120 sq ft
        - 1 kitchen of 110 sq ft
        - 2 bedrooms of 130 sq ft each
        - 1 bathroom of 50 sq ft
        Requirements:
        - Kitchen must be adjacent to bedroom
        - Private bedroom zone must be completely separated from kitchen noise
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_05_extreme_aspect_rooms",
        name="Constrained Aspect Ratio Room Program",
        description="Room dimensions approaching minimal allowable width (1.8m), testing aspect ratio bounds and door fitting.",
        category=FixtureCategory.COMPLEXITY_STRESS,
        expected_feasibility=FeasibilityExpectation.FEASIBLE_BUT_DIFFICULT,
        geometric_properties={
            "min_room_width_m": 1.8,
        },
        limitations=["Narrow room widths restrict door swing and furniture clearance"],
        brief="""
        Single floor urban infill on a 25 feet by 60 feet plot with front setback: 1.5m, rear setback: 1.5m, side setback: 1m.
        Floor 1:
        - 1 living room of 160 sq ft
        - 1 kitchen of 80 sq ft
        - 1 bedroom of 110 sq ft
        - 1 bathroom of 40 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_06_three_floor_vertical_stress",
        name="Three-Floor Residence with Vertical Circulation",
        description="Three-floor vertical circulation program testing multi-tier staircase alignment and floor-by-floor zoning.",
        category=FixtureCategory.COMPLEXITY_STRESS,
        expected_feasibility=FeasibilityExpectation.FEASIBLE,
        geometric_properties={
            "floors": 3,
            "staircases_required": 2,
        },
        limitations=["Staircase must align across all 3 levels"],
        brief="""
        Three floor townhouse on a 30 feet by 40 feet plot with front setback: 2m, rear setback: 2m, side setback: 1.5m.
        Floor 1:
        - 1 living room of 200 sq ft
        - 1 kitchen of 100 sq ft
        Floor 2:
        - 2 bedrooms of 120 sq ft each
        - 1 bathroom of 45 sq ft
        Floor 3:
        - 1 bedroom of 130 sq ft
        - 1 study of 100 sq ft
        - 1 bathroom of 45 sq ft
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_07_ambiguous_brief",
        name="Ambiguous Program Requiring Clarification",
        description="Brief missing mandatory room specifications, requiring interactive clarification before spatial allocation.",
        category=FixtureCategory.FEASIBILITY_LIMIT,
        expected_feasibility=FeasibilityExpectation.INSUFFICIENT_INFORMATION,
        geometric_properties={
            "missing_rooms": True,
        },
        limitations=["Cannot proceed to ASAA without room definitions"],
        brief="""
        Single floor modern residential villa on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Please create an open and spacious design with nice flow.
        """,
    ),
    RobustnessFixture(
        fixture_id="stress_08_unsupported_curved_geometry",
        name="Explicitly Unsupported Curved Plot Boundary",
        description="Circular curved plot boundary, verifying truthful rejection as unsupported input rather than generating an invalid design.",
        category=FixtureCategory.UNSUPPORTED_INPUT,
        expected_feasibility=FeasibilityExpectation.UNSUPPORTED_INPUT,
        geometric_properties={
            "plot_shape": "circular",
            "supported": False,
        },
        limitations=["PlanForge ASAA and Geometry Engine currently support rectilinear and non-convex polygonal plots only"],
        brief="""
        Single floor house on a circular plot of radius 15 meters with 2m setback all around.
        Floor 1:
        - 1 living room of 200 sq ft
        - 1 kitchen of 100 sq ft
        - 1 bedroom of 120 sq ft
        - 1 bathroom of 50 sq ft
        """,
    ),
]


class RobustnessRegistry:
    """Registry providing filtered access to generalization and stress test fixtures."""

    @classmethod
    def get_heldout_fixtures(cls) -> List[RobustnessFixture]:
        return list(HELDOUT_GEOMETRY_FIXTURES)

    @classmethod
    def get_stress_fixtures(cls) -> List[RobustnessFixture]:
        return list(COMPLEXITY_STRESS_FIXTURES)

    @classmethod
    def get_all_robustness_fixtures(cls) -> List[RobustnessFixture]:
        return list(HELDOUT_GEOMETRY_FIXTURES) + list(COMPLEXITY_STRESS_FIXTURES)

    @classmethod
    def get_fixture(cls, fixture_id: str) -> Optional[RobustnessFixture]:
        for f in cls.get_all_robustness_fixtures():
            if f.fixture_id == fixture_id:
                return f
        return None
