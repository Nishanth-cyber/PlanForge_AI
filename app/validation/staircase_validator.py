"""Staircase Validator for independent verification of vertical circulation geometry.

Independently checks:
- Required staircase existence
- Containment within ASAA staircase allocated region
- Non-degenerate footprint and positive riser/tread parameters
- Multi-floor vertical core alignment between connected floors
"""

from __future__ import annotations
from typing import List, Optional, Tuple
from shapely.geometry import Polygon

from app.geometry.geometry_utils import to_shapely_polygon
from app.models.allocation import Allocation, AllocationSet
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoStaircase
from app.models.planning import PlanningSpec
from app.models.validation import ValidationIssue


class StaircaseValidator:
    """Independently verifies physical staircase geometry and multi-floor alignment."""

    def __init__(self, alignment_tolerance_sqm: float = 0.10):
        """Initialize StaircaseValidator.

        Args:
            alignment_tolerance_sqm: Maximum symmetric difference area allowed between aligned floor footprints.
        """
        self.alignment_tolerance_sqm = alignment_tolerance_sqm

    def validate_floor(
        self,
        geometry: Geometry,
        allocation: Optional[Allocation] = None,
        is_staircase_required: bool = False,
    ) -> List[ValidationIssue]:
        """Validate staircase on a single floor.

        Args:
            geometry: Floor Geometry.
            allocation: Upstream ASAA allocation for this floor.
            is_staircase_required: Whether vertical core is required on this floor.

        Returns:
            List of ValidationIssue instances.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        # 1. Existence check
        if is_staircase_required and not geometry.staircases:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="staircase",
                    check="missing_staircase",
                    message=f"Floor {floor_num} requires vertical circulation, but no staircase was constructed",
                    floor_number=floor_num,
                )
            )
            return issues

        for stair in geometry.staircases:
            # 2. Footprint Validity
            if not stair.polygon or len(stair.polygon) < 3:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="staircase",
                        check="invalid_staircase_polygon",
                        message=f"Staircase (id={stair.id}) has degenerate footprint with fewer than 3 vertices",
                        target_id=stair.id,
                        floor_number=floor_num,
                    )
                )
                continue

            poly = to_shapely_polygon(stair.polygon)
            if not poly.is_valid or poly.area <= 0.5:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="staircase",
                        check="staircase_area",
                        message=f"Staircase (id={stair.id}) footprint area ({poly.area:.2f} sqm) is invalid or too small",
                        details={"area_sqm": round(poly.area, 2)},
                        target_id=stair.id,
                        floor_number=floor_num,
                    )
                )

            # 3. Riser and Tread checks
            if stair.riser_count < 10:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="staircase",
                        check="insufficient_risers",
                        message=f"Staircase (id={stair.id}) has only {stair.riser_count} risers (minimum 10 required)",
                        target_id=stair.id,
                        floor_number=floor_num,
                    )
                )

            if stair.tread_depth < 0.20:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="staircase",
                        check="insufficient_tread_depth",
                        message=f"Staircase (id={stair.id}) tread depth {stair.tread_depth:.2f}m is below minimum 0.20m",
                        target_id=stair.id,
                        floor_number=floor_num,
                    )
                )

            # 4. Containment within ASAA Staircase Allocation
            if allocation:
                stair_reg = allocation.get_staircase_region()
                if stair_reg and stair_reg.polygon and len(stair_reg.polygon) >= 3:
                    reg_poly = to_shapely_polygon(stair_reg.polygon).buffer(0.05)
                    if not (reg_poly.contains(poly) or reg_poly.covers(poly)):
                        spill = poly.difference(reg_poly)
                        if spill.area > 0.05:
                            issues.append(
                                ValidationIssue(
                                    severity="error",
                                    category="staircase",
                                    check="staircase_allocation_containment",
                                    message=(
                                        f"Staircase (id={stair.id}) extends outside assigned ASAA "
                                        f"staircase core (id={stair_reg.id}) by {spill.area:.2f} sqm"
                                    ),
                                    details={"allocated_region_id": stair_reg.id, "spill_area": round(spill.area, 3)},
                                    target_id=stair.id,
                                    floor_number=floor_num,
                                )
                            )

        return issues

    def validate_multi_floor_alignment(
        self,
        floor_plan_set: FloorPlanSet,
    ) -> List[ValidationIssue]:
        """Validate vertical alignment of staircases across connected floors.

        Args:
            floor_plan_set: Complete multi-floor plan set.

        Returns:
            List of ValidationIssue instances for any misalignment between floors.
        """
        issues: List[ValidationIssue] = []
        fps = sorted(floor_plan_set.floor_plans, key=lambda f: f.floor_number)
        if len(fps) < 2:
            return issues

        for i in range(len(fps) - 1):
            fp_lower = fps[i]
            fp_upper = fps[i + 1]

            if not fp_lower.geometry or not fp_upper.geometry:
                continue

            stairs_lower = fp_lower.geometry.staircases
            stairs_upper = fp_upper.geometry.staircases

            if not stairs_lower or not stairs_upper:
                continue

            poly_lower = to_shapely_polygon(stairs_lower[0].polygon)
            poly_upper = to_shapely_polygon(stairs_upper[0].polygon)

            # Check symmetric difference (discrepancy) area
            diff = poly_lower.symmetric_difference(poly_upper)
            if diff.area > self.alignment_tolerance_sqm:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="staircase",
                        check="vertical_staircase_misalignment",
                        message=(
                            f"Staircase vertical core is misaligned between Floor {fp_lower.floor_number} "
                            f"and Floor {fp_upper.floor_number} (discrepancy={diff.area:.2f} sqm)"
                        ),
                        details={
                            "lower_floor": fp_lower.floor_number,
                            "upper_floor": fp_upper.floor_number,
                            "discrepancy_area_sqm": round(diff.area, 3),
                        },
                        target_id=stairs_lower[0].id,
                        floor_number=fp_lower.floor_number,
                    )
                )

        return issues
