"""Deterministic residential benchmark dataset for PlanForge research evaluation."""

from __future__ import annotations

from typing import Dict, List, Optional
from app.evaluation.models import BenchmarkCase, BenchmarkCategory

BENCHMARK_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        case_id="case_01_small_single_floor",
        name="Small Single-Floor Bungalow",
        description="Compact 1-floor residence with essential living, kitchen, bedroom, and bathroom spaces.",
        difficulty="low",
        tags=[BenchmarkCategory.SINGLE_FLOOR],
        brief="""
        Single floor compact bungalow on a 35 feet by 45 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 220 sq ft
        - 1 kitchen of 120 sq ft
        - 1 bedroom of 150 sq ft
        - 1 bathroom of 50 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 4,
        },
    ),
    BenchmarkCase(
        case_id="case_02_medium_single_floor",
        name="Medium Single-Floor Suburban Residence",
        description="Standard suburban 3-bedroom single-level home with balanced public and private zones.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR],
        brief="""
        Single floor suburban home on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 280 sq ft
        - 1 dining room of 160 sq ft
        - 1 kitchen of 140 sq ft
        - 2 bedrooms of 160 sq ft each
        - 1 bathroom of 60 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 6,
        },
    ),
    BenchmarkCase(
        case_id="case_03_large_single_floor",
        name="Large Single-Floor Estate Villa",
        description="Expansive single-story luxury residence with extensive social, private, and service rooms.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR],
        brief="""
        Single floor luxury estate on a 60 feet by 60 feet plot with front setback: 2.5m, rear setback: 2.5m, side setback: 2m.
        Floor 1:
        - 1 foyer of 100 sq ft
        - 1 living room of 350 sq ft
        - 1 dining room of 200 sq ft
        - 1 kitchen of 180 sq ft
        - 3 bedrooms of 180 sq ft each
        - 2 bathrooms of 70 sq ft each
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 9,
        },
    ),
    BenchmarkCase(
        case_id="case_04_two_floor_family",
        name="Two-Floor Family Residence",
        description="Standard 2-floor family house with public ground floor, private upper floor, and vertical core.",
        difficulty="medium",
        tags=[BenchmarkCategory.MULTI_FLOOR, BenchmarkCategory.STAIRCASE],
        brief="""
        Two floor family residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 260 sq ft
        - 1 dining room of 150 sq ft
        - 1 kitchen of 140 sq ft
        Floor 2:
        - 2 bedrooms of 170 sq ft each
        - 1 bathroom of 65 sq ft
        """,
        expected_properties={
            "expected_floors": 2,
            "expected_feasibility": True,
            "requires_staircase": True,
            "min_rooms": 6,
        },
    ),
    BenchmarkCase(
        case_id="case_05_three_floor_townhouse",
        name="Three-Floor Urban Townhouse",
        description="Vertical townhouse across 3 levels requiring vertical circulation alignment across all floors.",
        difficulty="high",
        tags=[BenchmarkCategory.MULTI_FLOOR, BenchmarkCategory.STAIRCASE, BenchmarkCategory.TIGHT_SPACE],
        brief="""
        Three floor contemporary townhouse on a 30 feet by 45 feet plot with front setback: 1.5m, rear setback: 1.5m, side setback: 1.5m.
        Floor 1:
        - 1 living room of 220 sq ft
        - 1 kitchen of 120 sq ft
        Floor 2:
        - 1 master bedroom of 200 sq ft
        - 1 bathroom of 60 sq ft
        Floor 3:
        - 1 bedroom of 180 sq ft
        - 1 study of 120 sq ft
        """,
        expected_properties={
            "expected_floors": 3,
            "expected_feasibility": True,
            "requires_staircase": True,
            "min_rooms": 6,
        },
    ),
    BenchmarkCase(
        case_id="case_06_irregular_l_plot",
        name="Irregular L-Shaped Boundary Residence",
        description="Single-level residence on an L-shaped plot testing non-convex polygon containment.",
        difficulty="high",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.IRREGULAR_PLOT],
        brief="""
        Single floor home on an L-shaped plot of 50 feet by 50 feet with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 240 sq ft
        - 1 dining room of 140 sq ft
        - 1 kitchen of 130 sq ft
        - 1 bedroom of 160 sq ft
        - 1 bathroom of 55 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "plot_shape": "l-shaped",
            "min_rooms": 5,
        },
    ),
    BenchmarkCase(
        case_id="case_07_tight_urban",
        name="Constrained Narrow Urban Infill",
        description="Narrow urban lot with tight setback-to-envelope ratios.",
        difficulty="high",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.TIGHT_SPACE],
        brief="""
        Single floor narrow lot dwelling on a 25 feet by 40 feet plot with front setback: 1.5m, rear setback: 1.5m, side setback: 1.2m.
        Floor 1:
        - 1 living room of 180 sq ft
        - 1 kitchen of 100 sq ft
        - 1 bedroom of 130 sq ft
        - 1 bathroom of 45 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 4,
        },
    ),
    BenchmarkCase(
        case_id="case_08_multi_bedroom",
        name="Four-Bedroom Extended Family Layout",
        description="Single floor layout requiring clean partitioning between multiple private sleeping spaces.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR],
        brief="""
        Single floor residence on a 50 feet by 60 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 260 sq ft
        - 1 dining room of 150 sq ft
        - 1 kitchen of 140 sq ft
        - 4 bedrooms of 140 sq ft each
        - 2 bathrooms of 55 sq ft each
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 9,
        },
    ),
    BenchmarkCase(
        case_id="case_09_attached_suite",
        name="Master Bedroom Attached Suite",
        description="Layout with explicit attached bathroom constraint connected directly to the master bedroom.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.ATTACHED_SUITE],
        brief="""
        Single floor home on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 250 sq ft
        - 1 kitchen of 130 sq ft
        - 1 master bedroom of 180 sq ft attached to bathroom of 55 sq ft
        - 1 dining room of 140 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "has_attached_relationship": True,
            "min_rooms": 4,
        },
    ),
    BenchmarkCase(
        case_id="case_10_separation_heavy",
        name="Separation Heavy Acoustic Layout",
        description="House with explicit acoustic and functional separation requirements between service and private zones.",
        difficulty="high",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.SEPARATION_HEAVY],
        brief="""
        Single floor acoustic dwelling on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 260 sq ft
        - 1 kitchen of 140 sq ft separated from bedroom
        - 1 bedroom of 180 sq ft
        - 1 bathroom of 60 sq ft
        - 1 study of 120 sq ft separated from living room
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "has_separation_requirements": True,
            "min_rooms": 5,
        },
    ),
    BenchmarkCase(
        case_id="case_11_adjacency_heavy",
        name="Adjacency Heavy Social Flow",
        description="Layout with strict mandatory adjacencies between kitchen, dining, and living rooms.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.ADJACENCY_HEAVY],
        brief="""
        Single floor home on a 45 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 270 sq ft adjacent to dining room
        - 1 dining room of 160 sq ft adjacent to kitchen
        - 1 kitchen of 140 sq ft
        - 1 bedroom of 170 sq ft
        - 1 bathroom of 55 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "has_adjacency_requirements": True,
            "min_rooms": 5,
        },
    ),
    BenchmarkCase(
        case_id="case_12_preferred_relationships",
        name="Preferred Relationship Flexible Program",
        description="Home specifying soft advisory relationships between living spaces and bedrooms.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR],
        brief="""
        Single floor modern house on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 260 sq ft
        - 1 dining room of 150 sq ft
        - 1 kitchen of 140 sq ft
        - 2 bedrooms of 160 sq ft each
        - 1 bathroom of 60 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 6,
        },
    ),
    BenchmarkCase(
        case_id="case_13_staircase_core",
        name="Multi-Level Vertical Staircase Coordination",
        description="Two-floor residence testing vertical core alignment and staircase placement.",
        difficulty="medium",
        tags=[BenchmarkCategory.MULTI_FLOOR, BenchmarkCategory.STAIRCASE],
        brief="""
        Two floor modern residence on a 38 feet by 48 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 240 sq ft
        - 1 dining room of 140 sq ft
        - 1 kitchen of 120 sq ft
        Floor 2:
        - 2 bedrooms of 160 sq ft each
        - 1 bathroom of 60 sq ft
        """,
        expected_properties={
            "expected_floors": 2,
            "expected_feasibility": True,
            "requires_staircase": True,
            "min_rooms": 6,
        },
    ),
    BenchmarkCase(
        case_id="case_14_orientation_east",
        name="East-Facing Solar & Entrance Orientation",
        description="Residential brief with explicit East plot orientation and East entrance preference.",
        difficulty="medium",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.ORIENTATION],
        brief="""
        Single floor residence on an east facing plot of 40 feet by 50 feet with entrance facing east and front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 260 sq ft
        - 1 dining room of 150 sq ft
        - 1 kitchen of 130 sq ft
        - 1 bedroom of 160 sq ft
        - 1 bathroom of 55 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "orientation": "east",
            "entrance_facing": "east",
            "min_rooms": 5,
        },
    ),
    BenchmarkCase(
        case_id="case_15_feasibility_edge",
        name="High-Density Feasibility Edge Case",
        description="Tight program whose aggregate room areas approach the buildable area limit.",
        difficulty="high",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.FEASIBILITY_EDGE_CASE, BenchmarkCategory.TIGHT_SPACE],
        brief="""
        Single floor high-density bungalow on a 32 feet by 40 feet plot with front setback: 1.5m, rear setback: 1.5m, side setback: 1.5m.
        Floor 1:
        - 1 living room of 220 sq ft
        - 1 dining room of 120 sq ft
        - 1 kitchen of 110 sq ft
        - 1 bedroom of 140 sq ft
        - 1 bathroom of 50 sq ft
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": True,
            "min_rooms": 5,
        },
    ),
    BenchmarkCase(
        case_id="case_16_infeasible_deficit",
        name="Infeasible Room Deficit Program",
        description="Program whose required room areas mathematically exceed the buildable area of the plot.",
        difficulty="high",
        tags=[BenchmarkCategory.SINGLE_FLOOR, BenchmarkCategory.INFEASIBLE],
        brief="""
        Single floor residence on a 20 feet by 20 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 500 sq ft
        - 1 dining room of 300 sq ft
        - 1 kitchen of 250 sq ft
        - 2 bedrooms of 300 sq ft each
        """,
        expected_properties={
            "expected_floors": 1,
            "expected_feasibility": False,
            "expected_infeasible": True,
            "min_rooms": 5,
        },
    ),
]


class BenchmarkRegistry:
    """Registry providing lookup and filtered selection of benchmark cases."""

    _cases: Dict[str, BenchmarkCase] = {c.case_id: c for c in BENCHMARK_CASES}

    @classmethod
    def get_all_cases(cls) -> List[BenchmarkCase]:
        return list(cls._cases.values())

    @classmethod
    def get_case(cls, case_id: str) -> Optional[BenchmarkCase]:
        return cls._cases.get(case_id)

    @classmethod
    def filter_by_tags(cls, tags: List[BenchmarkCategory | str]) -> List[BenchmarkCase]:
        normalized_tags = [t.value if isinstance(t, BenchmarkCategory) else str(t) for t in tags]
        return [c for c in cls._cases.values() if any(c.has_tag(t) for t in normalized_tags)]

    @classmethod
    def filter_by_ids(cls, case_ids: List[str]) -> List[BenchmarkCase]:
        return [cls._cases[cid] for cid in case_ids if cid in cls._cases]
