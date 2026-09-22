"""Candidate generator for ASAA.

Generates multiple diverse spatial allocation candidates using distinct architectural
zoning strategies (front-to-back, lateral wings, radial core, orientation-aligned)
with deterministic seeds.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Optional, Tuple
from shapely.geometry import Polygon
from app.asaa.spatial_partitioner import PartitionItem, SpatialPartitioner
from app.models.planning import RoomSpec


@dataclass
class CandidateAllocation:
    """A candidate spatial allocation for a floor."""
    candidate_id: str
    strategy: str
    items: list[PartitionItem] = field(default_factory=list)
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    is_valid: bool = True
    rejection_reasons: list[str] = field(default_factory=list)


class CandidateGenerator:
    """Generates candidate spatial allocations using diverse architectural strategies."""

    STRATEGIES = [
        "front_to_back",
        "lateral",
        "radial",
        "orientation_aligned",
    ]

    @staticmethod
    def generate_candidates(
        buildable_polygon: Polygon,
        room_specs: list[RoomSpec],
        room_budgets: dict[str, float],
        has_staircase: bool = False,
        staircase_area_sqm: float = 8.0,
        staircase_anchor_polygon: Optional[list[Tuple[float, float]]] = None,
        circulation_area_sqm: float = 0.0,
        entrance_intent: Optional[dict] = None,
        num_candidates: int = 3,
        seed: int = 42,
    ) -> list[CandidateAllocation]:
        """Generate N diverse allocation candidates.

        Args:
            buildable_polygon: Usable buildable area polygon.
            room_specs: Room specifications for this floor.
            room_budgets: Area budget per room spec ID.
            has_staircase: Whether staircase zone is required.
            staircase_area_sqm: Reserved staircase area.
            staircase_anchor_polygon: Aligned staircase polygon from Floor 1.
            circulation_area_sqm: Circulation allowance in m².
            entrance_intent: Entrance intent dictionary.
            num_candidates: Number of candidates to generate (1 to 4).
            seed: Deterministic random seed.

        Returns:
            List of CandidateAllocation objects.
        """
        rng = random.Random(seed)
        strategies = list(CandidateGenerator.STRATEGIES[:max(1, min(num_candidates, len(CandidateGenerator.STRATEGIES)))])

        # If more candidates requested than strategies, cycle with slight room shuffling
        candidates: list[CandidateAllocation] = []

        for idx, strat in enumerate(strategies):
            cid = f"cand_{idx + 1}_{strat}"
            # Partition space using this strategy
            items = SpatialPartitioner.partition(
                buildable_polygon=buildable_polygon,
                room_specs=room_specs,
                room_budgets=room_budgets,
                has_staircase=has_staircase,
                staircase_area_sqm=staircase_area_sqm,
                staircase_anchor_polygon=staircase_anchor_polygon,
                circulation_area_sqm=circulation_area_sqm,
                entrance_intent=entrance_intent,
                zoning_strategy=strat,
            )

            candidates.append(
                CandidateAllocation(
                    candidate_id=cid,
                    strategy=strat,
                    items=items,
                )
            )

        return candidates
