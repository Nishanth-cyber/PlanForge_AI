"""Adaptive spatial allocation refiner for ASAA.

Performs allocation-level iterative improvements (room region swaps,
partition nudges) to improve relationship satisfaction, area matching,
and orientation alignment without modifying architectural geometry (no doors/walls).
"""

from __future__ import annotations
import copy
from typing import Optional
from shapely.geometry import Polygon
from app.asaa.candidate_generator import CandidateAllocation
from app.asaa.scoring import CandidateScorer
from app.models.planning import FloorPlanSpec, RoomSpec


class AdaptiveRefiner:
    """Performs allocation-level adaptive refinement on candidate allocations."""

    @staticmethod
    def refine(
        candidate: CandidateAllocation,
        buildable_polygon: Polygon,
        room_specs: list[RoomSpec],
        floor_plan_spec: Optional[FloorPlanSpec] = None,
        max_iterations: int = 10,
    ) -> CandidateAllocation:
        """Iteratively refine candidate allocation using allocation-level operations.

        Args:
            candidate: Initial CandidateAllocation.
            buildable_polygon: Buildable footprint boundary.
            room_specs: Room specifications.
            floor_plan_spec: FloorPlanSpec with relationship matrices.
            max_iterations: Max improvement iterations.

        Returns:
            Refined CandidateAllocation (improved or identical).
        """
        best_candidate = candidate
        current_items = copy.deepcopy(candidate.items)

        # Baseline evaluation
        is_valid, current_score, breakdown, rejections = CandidateScorer.evaluate(
            current_items, buildable_polygon, room_specs, floor_plan_spec
        )
        best_candidate.score = current_score
        best_candidate.score_breakdown = breakdown
        best_candidate.is_valid = is_valid
        best_candidate.rejection_reasons = rejections

        spec_map = {rs.id: rs for rs in room_specs}

        # Room items that are eligible for swapping (only "room" zone_type, not staircase/circulation)
        room_indices = [
            i for i, it in enumerate(current_items)
            if it.zone_type == "room" and it.room_spec_id in spec_map
        ]

        if len(room_indices) < 2:
            return best_candidate

        # Iterative swap improvement loop
        for iteration in range(max_iterations):
            improved = False

            for idx_a in range(len(room_indices)):
                i = room_indices[idx_a]
                item_a = current_items[i]
                spec_a = spec_map.get(item_a.room_spec_id)

                for idx_b in range(idx_a + 1, len(room_indices)):
                    j = room_indices[idx_b]
                    item_b = current_items[j]
                    spec_b = spec_map.get(item_b.room_spec_id)

                    if not spec_a or not spec_b:
                        continue

                    # Check area compatibility: can item_a fit into region_b and vice-versa?
                    area_poly_b = item_b.allocated_area_sqm
                    area_poly_a = item_a.allocated_area_sqm

                    # If min_area is violated by swapping, don't swap
                    if spec_a.min_area_sqm and area_poly_b < (spec_a.min_area_sqm - 0.1):
                        continue
                    if spec_b.min_area_sqm and area_poly_a < (spec_b.min_area_sqm - 0.1):
                        continue

                    # Try hypothetical swap of spatial assignments
                    trial_items = copy.deepcopy(current_items)
                    # Swap polygons and centroids
                    trial_items[i].polygon, trial_items[j].polygon = trial_items[j].polygon, trial_items[i].polygon
                    trial_items[i].centroid, trial_items[j].centroid = trial_items[j].centroid, trial_items[i].centroid
                    trial_items[i].allocated_area_sqm, trial_items[j].allocated_area_sqm = (
                        trial_items[j].allocated_area_sqm,
                        trial_items[i].allocated_area_sqm,
                    )

                    t_valid, t_score, t_breakdown, t_rejections = CandidateScorer.evaluate(
                        trial_items, buildable_polygon, room_specs, floor_plan_spec
                    )

                    # If trial improves score and remains valid
                    if t_valid and t_score > current_score + 0.5:
                        current_items = trial_items
                        current_score = t_score
                        breakdown = t_breakdown
                        rejections = t_rejections
                        improved = True
                        break

                if improved:
                    break

            if not improved:
                # Plateau reached
                break

        refined_candidate = CandidateAllocation(
            candidate_id=f"{candidate.candidate_id}_refined",
            strategy=candidate.strategy,
            items=current_items,
            score=current_score,
            score_breakdown=breakdown,
            is_valid=is_valid,
            rejection_reasons=rejections,
        )
        return refined_candidate
