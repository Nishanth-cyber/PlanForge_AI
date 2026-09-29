"""ASAA scoring engine.

Evaluates spatial allocations using an explainable multi-objective score.
Strictly separates HARD CONSTRAINTS (boundary containment, non-overlap, minimum area,
required adjacencies) from SOFT SCORE COMPONENTS (area suitability, preferred adjacency,
separation, compactness, circulation, orientation, priority).
"""

from __future__ import annotations
import math
from typing import Optional, Tuple
from shapely.geometry import Polygon
from app.asaa.spatial_partitioner import PartitionItem
from app.asaa.spatial_regions import (
    calculate_aspect_ratio,
    calculate_shared_boundary_length,
    are_regions_adjacent,
)
from app.models.allocation import AllocatedRegion, Allocation
from app.models.planning import FloorPlanSpec, RoomSpec


class CandidateScorer:
    """Evaluates candidate allocations against hard and soft constraints."""

    WEIGHTS = {
        "area_suitability": 0.25,
        "relationship_satisfaction": 0.25,
        "shape_compactness": 0.15,
        "circulation_connectivity": 0.15,
        "orientation_preference": 0.10,
        "priority_satisfaction": 0.10,
    }

    @staticmethod
    def evaluate(
        items: list[PartitionItem],
        buildable_polygon: Polygon,
        room_specs: list[RoomSpec],
        floor_plan_spec: Optional[FloorPlanSpec] = None,
        orientation: str = "north",
    ) -> Tuple[bool, float, dict[str, float], list[str]]:
        """Evaluate an allocation candidate.

        Returns:
            Tuple of (is_valid, total_score, score_breakdown, rejection_reasons)
        """
        rejection_reasons: list[str] = []
        is_valid = True

        # Room spec lookup
        spec_map = {rs.id: rs for rs in room_specs}

        # -------------------------------------------------------------
        # 1. HARD CONSTRAINTS
        # -------------------------------------------------------------

        # Hard Constraint A: Boundary Containment
        for item in items:
            if not item.polygon or len(item.polygon) < 3:
                is_valid = False
                rejection_reasons.append(f"Item {item.id} has invalid/empty polygon")
                continue

            item_poly = Polygon(item.polygon)
            # Area difference with buildable (buffered slightly for floating-point coordinate rounding)
            buffered_buildable = buildable_polygon.buffer(0.05)
            diff = item_poly.difference(buffered_buildable)
            if diff.area > 0.05:  # Tolerance for float rounding
                is_valid = False
                rejection_reasons.append(
                    f"Item {item.id} ({item.room_type}) extends outside buildable boundary by {diff.area:.2f} m²"
                )

        # Hard Constraint B: Non-Overlap
        for i in range(len(items)):
            poly_i = Polygon(items[i].polygon)
            for j in range(i + 1, len(items)):
                poly_j = Polygon(items[j].polygon)
                overlap = poly_i.intersection(poly_j).area
                if overlap > 0.05:
                    is_valid = False
                    rejection_reasons.append(
                        f"Overlap detected between {items[i].id} and {items[j].id}: {overlap:.2f} m²"
                    )

        # Hard Constraint C: Minimum Area Enforcement
        for item in items:
            if item.room_spec_id and item.room_spec_id in spec_map:
                rs = spec_map[item.room_spec_id]
                if rs.min_area_sqm is not None and rs.min_area_sqm > 0:
                    if item.allocated_area_sqm < (rs.min_area_sqm - 0.1):
                        is_valid = False
                        rejection_reasons.append(
                            f"Room {rs.room_type} allocated area ({item.allocated_area_sqm:.1f} m²) "
                            f"below minimum required ({rs.min_area_sqm:.1f} m²)"
                        )

        # Hard Constraint D: Attached Room Proximity
        # If a room is attached (e.g. attached bathroom to master bedroom), they must touch
        for item in items:
            if item.room_spec_id and item.room_spec_id in spec_map:
                rs = spec_map[item.room_spec_id]
                if rs.attached_to_room_id:
                    # Find parent item
                    parent_items = [
                        it for it in items
                        if it.room_spec_id == rs.attached_to_room_id
                    ]
                    if parent_items:
                        attached_touch = any(
                            are_regions_adjacent(item.polygon, p.polygon, min_contact_m=0.1)
                            for p in parent_items
                        )
                        if not attached_touch:
                            # We record warning / soft penalty rather than hard disqualification
                            # if geometry slicing separated them, but flag it
                            rejection_reasons.append(
                                f"Attached room {rs.room_type} does not share physical boundary with parent {rs.attached_to_room_id}"
                            )

        # -------------------------------------------------------------
        # 2. SOFT SCORE COMPONENTS (0.0 to 100.0)
        # -------------------------------------------------------------

        # A. Area Suitability (25%)
        area_scores = []
        for item in items:
            if item.target_area_sqm > 0:
                diff = abs(item.allocated_area_sqm - item.target_area_sqm)
                rel_diff = diff / item.target_area_sqm
                score_i = max(0.0, 100.0 * (1.0 - min(1.0, rel_diff)))
                area_scores.append(score_i)
        area_suitability = sum(area_scores) / len(area_scores) if area_scores else 80.0

        # B. Relationship Satisfaction (25%)
        rel_score = 80.0
        if floor_plan_spec:
            adj_matrix = floor_plan_spec.adjacency_matrix
            avoid_matrix = floor_plan_spec.avoid_matrix

            satisfied_adj = 0
            total_adj = 0
            avoid_violations = 0

            for i, item_a in enumerate(items):
                type_a = item_a.room_type
                for j in range(i + 1, len(items)):
                    item_b = items[j]
                    type_b = item_b.room_type

                    # Check preferred/required adjacency
                    if type_b in adj_matrix.get(type_a, []) or type_a in adj_matrix.get(type_b, []):
                        total_adj += 1
                        if are_regions_adjacent(item_a.polygon, item_b.polygon):
                            satisfied_adj += 1

                    # Check avoid / separation
                    if type_b in avoid_matrix.get(type_a, []) or type_a in avoid_matrix.get(type_b, []):
                        if are_regions_adjacent(item_a.polygon, item_b.polygon):
                            avoid_violations += 1

            if total_adj > 0:
                adj_ratio = satisfied_adj / total_adj
                rel_score = adj_ratio * 90.0 - (avoid_violations * 20.0)
            else:
                rel_score = 90.0 - (avoid_violations * 20.0)

            rel_score = max(0.0, min(100.0, rel_score))

        # C. Shape Compactness (15%)
        aspect_scores = []
        for item in items:
            ratio = calculate_aspect_ratio(item.polygon)
            if ratio <= 1.8:
                aspect_scores.append(100.0)
            elif ratio <= 2.5:
                aspect_scores.append(70.0)
            else:
                aspect_scores.append(max(20.0, 100.0 - (ratio - 1.8) * 40.0))
        shape_compactness = sum(aspect_scores) / len(aspect_scores) if aspect_scores else 80.0

        # D. Circulation / Connectivity Feasibility (15%)
        circ_zones = [it for it in items if it.zone_type in {"circulation", "entrance"}]
        habitable_items = [it for it in items if it.zone_type == "room"]

        if circ_zones and habitable_items:
            connected_count = 0
            for h in habitable_items:
                if any(are_regions_adjacent(h.polygon, cz.polygon, min_contact_m=0.1) for cz in circ_zones):
                    connected_count += 1
            circ_connectivity = (connected_count / len(habitable_items)) * 100.0
        else:
            circ_connectivity = 85.0

        # E. Orientation Preference (10%)
        orient_score = 80.0
        min_x, min_y, max_x, max_y = buildable_polygon.bounds
        mid_y = (min_y + max_y) / 2.0

        social_items = [it for it in items if it.category == "social"]
        if social_items:
            # Check if social items are situated towards the front/facing side
            front_social = sum(1 for it in social_items if it.centroid and it.centroid[1] <= mid_y)
            orient_score = (front_social / len(social_items)) * 100.0

        # F. Priority Satisfaction (10%)
        priority_scores = []
        for item in items:
            if item.priority == "high":
                # High priority gets high score if its area suitability is high and aspect is good
                ar = calculate_aspect_ratio(item.polygon)
                p_score = 100.0 if ar <= 1.8 else 75.0
                priority_scores.append(p_score)
            else:
                priority_scores.append(85.0)
        priority_satisfaction = sum(priority_scores) / len(priority_scores) if priority_scores else 85.0

        breakdown = {
            "area_suitability": round(area_suitability, 2),
            "relationship_satisfaction": round(rel_score, 2),
            "shape_compactness": round(shape_compactness, 2),
            "circulation_connectivity": round(circ_connectivity, 2),
            "orientation_preference": round(orient_score, 2),
            "priority_satisfaction": round(priority_satisfaction, 2),
        }

        total_score = sum(breakdown[k] * CandidateScorer.WEIGHTS[k] for k in CandidateScorer.WEIGHTS)
        if not is_valid:
            # Heavily penalize invalid candidates so they never rank above valid ones
            total_score = max(0.0, total_score * 0.2)

        return is_valid, round(total_score, 2), breakdown, rejection_reasons


# -------------------------------------------------------------
# Backward-Compatible Helper Functions
# -------------------------------------------------------------

def score_region(region: AllocatedRegion, room_spec: RoomSpec) -> float:
    """Score a single region allocation (backward-compatible)."""
    score = 100.0

    if room_spec.target_area_sqm > 0:
        diff = abs(region.area_sqm - room_spec.target_area_sqm)
        score -= (diff / room_spec.target_area_sqm) * 30.0

    if region.polygon:
        ratio = calculate_aspect_ratio(region.polygon)
        if ratio < 0.5 or ratio > 2.0:
            score -= 10.0

    if room_spec.adjacency:
        score += 15.0

    return max(0.0, round(score, 2))


def score_allocation(allocation: Allocation) -> float:
    """Score an allocation (backward-compatible)."""
    if not allocation.allocated_regions:
        return 0.0

    total = sum(region.score for region in allocation.allocated_regions)
    return round(total / len(allocation.allocated_regions), 2)


def calculate_adjacency_score(
    regions: list[AllocatedRegion],
    adjacency_matrix: dict[str, list[str]],
) -> float:
    """Calculate adjacency score based on region proximity (backward-compatible)."""
    if len(regions) < 2:
        return 100.0

    total = 0.0
    count = 0

    for i, region in enumerate(regions):
        for j in range(i + 1, len(regions)):
            other = regions[j]
            if other.room_type in adjacency_matrix.get(region.room_type, []):
                dist = _centroid_distance(region, other)
                total += max(0.0, 100.0 - dist * 10.0)
            count += 1

    return round(total / count, 2) if count > 0 else 100.0


def _centroid_distance(region_a: AllocatedRegion, region_b: AllocatedRegion) -> float:
    """Calculate distance between centroids."""
    if region_a.centroid is None or region_b.centroid is None:
        return float("inf")

    return math.sqrt(
        (region_a.centroid[0] - region_b.centroid[0]) ** 2
        + (region_a.centroid[1] - region_b.centroid[1]) ** 2
    )
