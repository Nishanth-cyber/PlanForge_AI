"""ASAA (Adaptive Space Allocation Algorithm) Allocator.

Orchestrates spatial budgeting, multi-strategy candidate generation,
computational space-filling partitioning, candidate scoring, and adaptive refinement.
Emits abstract spatial regions (WHERE) without generating final architectural geometry (HOW).
"""

from __future__ import annotations
from typing import Any, Optional, Tuple
from shapely.geometry import Polygon
from app.asaa.area_budgeter import AreaBudgeter
from app.asaa.boundary import BuildableBoundaryCalculator, BuildableBoundary
from app.asaa.candidate_generator import CandidateGenerator
from app.asaa.exceptions import InfeasibleAllocationError
from app.asaa.refiner import AdaptiveRefiner
from app.asaa.scoring import CandidateScorer
from app.asaa.spatial_regions import (
    calculate_approximate_dimensions,
    calculate_centroid,
    are_regions_adjacent,
)
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.utils.ids import generate_id


class ASAAAllocator:
    """Adaptive Space Allocation Algorithm.

    Allocates abstract 2D spatial regions for rooms, circulation, entrance,
    and vertical staircase zones across single and multi-floor buildings.
    Strictly answers WHERE spaces are located without generating architectural geometry.
    """

    def __init__(self, num_candidates: int = 3, seed: int = 42):
        """Initialize ASAA Allocator.

        Args:
            num_candidates: Number of allocation candidates to evaluate per floor.
            seed: Seed for deterministic candidate generation.
        """
        self.num_candidates = num_candidates
        self.seed = seed

    def allocate(
        self,
        planning_spec: PlanningSpec,
        num_candidates: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> AllocationSet:
        """Allocate spatial regions for all floors in the PlanningSpec.

        Args:
            planning_spec: Validated PlanningSpec from the Planning Agent.
            num_candidates: Optional candidate count override.
            seed: Optional seed override.

        Returns:
            AllocationSet containing complete allocations per floor.

        Raises:
            InfeasibleAllocationError: If requirements cannot be accommodated in buildable area.
            BoundaryConstraintError: If plot boundary or setbacks are geometrically invalid.
        """
        n_cands = num_candidates if num_candidates is not None else self.num_candidates
        use_seed = seed if seed is not None else self.seed

        # 1. Derive buildable boundary from planning_spec global constraints
        buildable = self._derive_buildable_boundary(planning_spec)

        allocation_set = AllocationSet(
            planning_spec_id=planning_spec.id,
        )

        is_multi_floor = len(planning_spec.floors) >= 2
        anchor_staircase_polygon: Optional[list[Tuple[float, float]]] = None
        staircase_aligned = False

        # 2. Allocate each floor independently while coordinating vertical core
        for floor_spec in planning_spec.floors:
            # Check staircase requirement
            has_stair = False
            if floor_spec.staircase_intent and floor_spec.staircase_intent.get("required"):
                has_stair = True
            elif is_multi_floor:
                has_stair = True

            allocation, stair_poly = self._allocate_floor(
                floor_spec=floor_spec,
                planning_spec=planning_spec,
                buildable=buildable,
                has_staircase=has_stair,
                anchor_staircase_polygon=anchor_staircase_polygon,
                num_candidates=n_cands,
                seed=use_seed,
            )

            # Coordinate vertical circulation across floors
            if has_stair and stair_poly:
                if anchor_staircase_polygon is None:
                    anchor_staircase_polygon = stair_poly
                else:
                    # Verified alignment with Floor 1
                    if anchor_staircase_polygon == stair_poly:
                        staircase_aligned = True

            allocation_set.allocations.append(allocation)

        if is_multi_floor and anchor_staircase_polygon is not None:
            allocation_set.staircase_aligned = staircase_aligned

        return allocation_set

    def _allocate_floor(
        self,
        floor_spec: FloorPlanSpec,
        planning_spec: PlanningSpec,
        buildable: BuildableBoundary,
        has_staircase: bool,
        anchor_staircase_polygon: Optional[list[Tuple[float, float]]],
        num_candidates: int,
        seed: int,
    ) -> Tuple[Allocation, Optional[list[Tuple[float, float]]]]:
        """Allocate regions for a single floor."""
        # 1. Compute Area Budget
        budget = AreaBudgeter.compute_budget(
            buildable_area_sqm=buildable.area_sqm,
            room_specs=floor_spec.room_specs,
            floor_number=floor_spec.floor_number,
            circulation_ratio=0.12,
            has_staircase=has_staircase,
            staircase_area_sqm=8.0,
        )

        # 2. Generate Candidate Allocations
        orientation = planning_spec.global_constraints.get("orientation", "north")
        candidates = CandidateGenerator.generate_candidates(
            buildable_polygon=buildable.shapely_polygon,
            room_specs=floor_spec.room_specs,
            room_budgets=budget.room_budgets,
            has_staircase=has_staircase,
            staircase_area_sqm=budget.staircase_area_sqm,
            staircase_anchor_polygon=anchor_staircase_polygon,
            circulation_area_sqm=budget.circulation_area_sqm,
            entrance_intent=floor_spec.entrance_intent if floor_spec.floor_number == 1 else None,
            num_candidates=num_candidates,
            seed=seed,
        )

        # 3. Score and Refine each candidate
        evaluated_candidates = []
        for cand in candidates:
            # Baseline scoring
            is_val, score, breakdown, rejections = CandidateScorer.evaluate(
                items=cand.items,
                buildable_polygon=buildable.shapely_polygon,
                room_specs=floor_spec.room_specs,
                floor_plan_spec=floor_spec,
                orientation=orientation,
            )
            cand.is_valid = is_val
            cand.score = score
            cand.score_breakdown = breakdown
            cand.rejection_reasons = rejections

            # Adaptive Refinement
            refined = AdaptiveRefiner.refine(
                candidate=cand,
                buildable_polygon=buildable.shapely_polygon,
                room_specs=floor_spec.room_specs,
                floor_plan_spec=floor_spec,
                max_iterations=8,
            )
            evaluated_candidates.append(refined)

        # 4. Select best candidate
        # Prefer valid candidates with highest score
        valid_cands = [c for c in evaluated_candidates if c.is_valid]
        if valid_cands:
            best_candidate = max(valid_cands, key=lambda c: c.score)
        else:
            best_candidate = max(evaluated_candidates, key=lambda c: c.score)

        # 5. Convert PartitionItems into AllocatedRegion objects
        allocated_regions = []
        staircase_poly = None

        for item in best_candidate.items:
            approx_dims = calculate_approximate_dimensions(item.polygon)
            centroid = item.centroid or calculate_centroid(item.polygon)

            region = AllocatedRegion(
                id=generate_id("region"),
                room_type=item.room_type,
                room_spec_id=item.room_spec_id,
                floor_number=floor_spec.floor_number,
                target_area_sqm=item.target_area_sqm,
                area_sqm=item.allocated_area_sqm,
                approximate_dimensions=approx_dims,
                polygon=item.polygon,
                centroid=centroid,
                priority=item.priority,
                zone_type=item.zone_type,
                score=best_candidate.score,
            )
            allocated_regions.append(region)

            if item.zone_type == "staircase":
                staircase_poly = item.polygon

        # 6. Populate shared boundary adjacency IDs between regions
        for i in range(len(allocated_regions)):
            reg_i = allocated_regions[i]
            for j in range(i + 1, len(allocated_regions)):
                reg_j = allocated_regions[j]
                if are_regions_adjacent(reg_i.polygon, reg_j.polygon, min_contact_m=0.1):
                    reg_i.adjacency_regions.append(reg_j.id)
                    reg_j.adjacency_regions.append(reg_i.id)

        # 7. Assemble Allocation
        total_area = sum(r.area_sqm for r in allocated_regions)
        circ_area = sum(
            r.area_sqm for r in allocated_regions if r.zone_type in {"circulation", "entrance"}
        )

        allocation = Allocation(
            floor_number=floor_spec.floor_number,
            floor_name=floor_spec.floor_name or f"Floor {floor_spec.floor_number}",
            total_area_sqm=round(total_area, 2),
            allocated_regions=allocated_regions,
            circulation_area_sqm=round(circ_area, 2),
            score=best_candidate.score,
            algorithm_version="2.0-ASAA",
        )

        return allocation, staircase_poly

    def _derive_buildable_boundary(self, planning_spec: PlanningSpec) -> BuildableBoundary:
        """Derive buildable boundary from planning spec global constraints."""
        gc = planning_spec.global_constraints
        plot_poly = gc.get("plot_polygon") or gc.get("plot_shape")
        plot_area = gc.get("plot_area_sqm")
        plot_w = gc.get("plot_width_m")
        plot_d = gc.get("plot_depth_m")
        if (plot_w is None or plot_d is None) and gc.get("plot_dimensions"):
            plot_w, plot_d = gc["plot_dimensions"]
        setbacks = gc.get("setbacks")

        return BuildableBoundaryCalculator.calculate(
            plot_polygon=plot_poly,
            plot_area_sqm=plot_area,
            plot_width_m=plot_w,
            plot_depth_m=plot_d,
            setbacks=setbacks,
        )