"""Baseline spatial allocator for PlanForge research evaluation.

Provides a deterministic, priority-blind, proportional spatial partitioning reference
implementation to isolate and evaluate the specific contributions of ASAA.

Architecture & Baseline Design:
1. Derives the identical buildable boundary from PlanningSpec using BuildableBoundaryCalculator.
2. Checks basic feasibility (ensuring total room minimum areas do not exceed buildable area).
3. Allocates space priority-blind in room sequence.
4. Uses straightforward proportional 1D slicing across the buildable boundary bounding box.
5. Does NOT perform multi-candidate generation, does NOT score spatial relationship attraction/repulsion,
   does NOT evaluate entrance proximity or solar orientation, and does NOT perform adaptive boundary refinement.
6. Returns standard AllocationSet and AllocatedRegion instances compatible with downstream pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import Polygon, box

from app.asaa.boundary import BuildableBoundary, BuildableBoundaryCalculator
from app.asaa.exceptions import InfeasibleAllocationError
from app.asaa.spatial_regions import (
    are_regions_adjacent,
    calculate_approximate_dimensions,
    calculate_centroid,
)
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.utils.ids import generate_id


class BaselineSpatialAllocator:
    """Evaluation-only baseline allocator implementing priority-blind proportional slicing."""

    def __init__(self, algorithm_version: str = "Baseline-ProportionalSlice") -> None:
        self.algorithm_version = algorithm_version

    def allocate(
        self,
        planning_spec: PlanningSpec,
        num_candidates: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> AllocationSet:
        """Allocate spatial regions using deterministic proportional slicing.

        Args:
            planning_spec: Validated PlanningSpec from the Planning Agent.
            num_candidates: Ignored by baseline (always deterministic single-pass).
            seed: Ignored by baseline (fully deterministic).

        Returns:
            AllocationSet containing complete baseline allocations.

        Raises:
            InfeasibleAllocationError: If requirements exceed buildable boundary.
        """
        buildable = self._derive_buildable_boundary(planning_spec)
        allocation_set = AllocationSet(planning_spec_id=planning_spec.id)

        is_multi_floor = len(planning_spec.floors) >= 2
        staircase_anchor: Optional[Polygon] = None

        for floor_spec in planning_spec.floors:
            has_stair = False
            if floor_spec.staircase_intent and floor_spec.staircase_intent.get("required"):
                has_stair = True
            elif is_multi_floor:
                has_stair = True

            allocation, stair_poly = self._allocate_floor(
                floor_spec=floor_spec,
                buildable=buildable,
                has_staircase=has_stair,
                staircase_anchor=staircase_anchor,
            )

            if has_stair and stair_poly is not None and staircase_anchor is None:
                staircase_anchor = stair_poly

            allocation_set.allocations.append(allocation)

        if is_multi_floor and staircase_anchor is not None:
            allocation_set.staircase_aligned = True

        return allocation_set

    def _allocate_floor(
        self,
        floor_spec: FloorPlanSpec,
        buildable: BuildableBoundary,
        has_staircase: bool,
        staircase_anchor: Optional[Polygon],
    ) -> Tuple[Allocation, Optional[Polygon]]:
        """Proportionally slice the buildable area across required room specs."""
        room_specs = floor_spec.room_specs
        if not room_specs:
            return Allocation(
                floor_number=floor_spec.floor_number,
                floor_name=floor_spec.floor_name or f"Floor {floor_spec.floor_number}",
                total_area_sqm=0.0,
                allocated_regions=[],
                score=50.0,
                algorithm_version=self.algorithm_version,
            ), None

        # 1. Feasibility check
        total_min_area = sum(
            (r.min_area_sqm if r.min_area_sqm is not None else (r.target_area_sqm or 5.0))
            for r in room_specs
        )
        staircase_area = 8.0 if has_staircase else 0.0
        available_area = buildable.area_sqm

        if total_min_area + staircase_area > available_area:
            raise InfeasibleAllocationError(
                f"Floor {floor_spec.floor_number}: Total minimum room area ({total_min_area + staircase_area:.1f} m²) "
                f"exceeds available buildable area ({available_area:.1f} m²)"
            )

        min_x, min_y, max_x, max_y = buildable.shapely_polygon.bounds
        total_w = max(1.0, max_x - min_x)
        total_h = max(1.0, max_y - min_y)

        allocated_regions: List[AllocatedRegion] = []
        stair_poly_result: Optional[Polygon] = None

        # 2. Allocate fixed staircase zone if required (corner placement for multi-floor)
        rem_min_x = min_x
        rem_max_x = max_x
        rem_min_y = min_y
        rem_max_y = max_y

        if has_staircase:
            stair_w = min(3.0, total_w * 0.25)
            stair_h = min(total_h, max(2.5, 8.0 / stair_w))
            stair_box = box(min_x, min_y, min_x + stair_w, min_y + stair_h)
            stair_poly_result = stair_box

            stair_coords = [(round(x, 4), round(y, 4)) for x, y in stair_box.exterior.coords[:-1]]
            stair_region = AllocatedRegion(
                id=generate_id("region"),
                room_type="staircase",
                floor_number=floor_spec.floor_number,
                target_area_sqm=round(stair_box.area, 2),
                area_sqm=round(stair_box.area, 2),
                approximate_dimensions=calculate_approximate_dimensions(stair_coords),
                polygon=stair_coords,
                zone_type="staircase",
            )
            allocated_regions.append(stair_region)
            rem_min_x = min_x + stair_w

        # 3. Proportionally slice remaining space along primary axis
        # Calculate target weights priority-blind
        target_areas = [
            (r.target_area_sqm if r.target_area_sqm is not None else (r.min_area_sqm or 10.0))
            for r in room_specs
        ]
        total_target = sum(target_areas) if sum(target_areas) > 0 else float(len(room_specs))

        slice_w = max(0.5, rem_max_x - rem_min_x)
        slice_h = max(0.5, rem_max_y - rem_min_y)

        # Slice along the longer axis
        slice_vertically = slice_w >= slice_h

        curr_offset = rem_min_x if slice_vertically else rem_min_y

        for i, r_spec in enumerate(room_specs):
            fraction = target_areas[i] / total_target
            if i == len(room_specs) - 1:
                # Last slice takes remainder
                if slice_vertically:
                    seg_poly = box(curr_offset, rem_min_y, rem_max_x, rem_max_y)
                else:
                    seg_poly = box(rem_min_x, curr_offset, rem_max_x, rem_max_y)
            else:
                if slice_vertically:
                    seg_len = fraction * slice_w
                    seg_poly = box(curr_offset, rem_min_y, curr_offset + seg_len, rem_max_y)
                    curr_offset += seg_len
                else:
                    seg_len = fraction * slice_h
                    seg_poly = box(rem_min_x, curr_offset, rem_max_x, curr_offset + seg_len)
                    curr_offset += seg_len

            # Intersect with buildable boundary to handle irregular bounds
            clipped = seg_poly.intersection(buildable.shapely_polygon)
            final_poly = clipped if not clipped.is_empty and clipped.area > 0.1 else seg_poly

            if final_poly.geom_type != "Polygon":
                final_poly = final_poly.convex_hull

            coords = [(round(x, 4), round(y, 4)) for x, y in final_poly.exterior.coords[:-1]]
            area_sqm = round(final_poly.area, 2)

            reg = AllocatedRegion(
                id=generate_id("region"),
                room_type=r_spec.room_type,
                room_spec_id=r_spec.id,
                floor_number=floor_spec.floor_number,
                target_area_sqm=r_spec.target_area_sqm or area_sqm,
                area_sqm=area_sqm,
                approximate_dimensions=calculate_approximate_dimensions(coords),
                polygon=coords,
                zone_type=getattr(r_spec, "room_category", "room") or "room",
                priority=r_spec.priority or "normal",
            )
            allocated_regions.append(reg)

        # 4. Shared boundary adjacencies
        for i in range(len(allocated_regions)):
            reg_i = allocated_regions[i]
            for j in range(i + 1, len(allocated_regions)):
                reg_j = allocated_regions[j]
                if are_regions_adjacent(reg_i.polygon, reg_j.polygon, min_contact_m=0.1):
                    reg_i.adjacency_regions.append(reg_j.id)
                    reg_j.adjacency_regions.append(reg_i.id)

        tot_area = sum(r.area_sqm for r in allocated_regions)
        circ_area = sum(r.area_sqm for r in allocated_regions if r.zone_type in {"circulation", "entrance", "staircase"})

        allocation = Allocation(
            floor_number=floor_spec.floor_number,
            floor_name=floor_spec.floor_name or f"Floor {floor_spec.floor_number}",
            total_area_sqm=round(tot_area, 2),
            allocated_regions=allocated_regions,
            circulation_area_sqm=round(circ_area, 2),
            score=50.0,
            algorithm_version=self.algorithm_version,
        )

        return allocation, stair_poly_result

    def _derive_buildable_boundary(self, planning_spec: PlanningSpec) -> BuildableBoundary:
        """Derive buildable boundary matching ASAA calculation."""
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
