"""Dimension Validator for independent evaluation of room areas and dimensions.

Validates that constructed room usable areas satisfy hard minimum area requirements
and reports advisory warnings for significant deviations from preferred target areas.
"""

from __future__ import annotations
from typing import Dict, List, Optional

from app.models.geometry import Geometry, GeoRoom
from app.models.planning import FloorPlanSpec, RoomSpec
from app.models.requirements import FloorRequirements, RoomRequirement
from app.models.validation import ValidationIssue


class DimensionValidator:
    """Independently verifies room areas and dimensional constraints."""

    def __init__(self, hard_tolerance: float = 0.05, soft_deviation_threshold: float = 0.25):
        """Initialize DimensionValidator.

        Args:
            hard_tolerance: Permissible fractional deficit on minimum area (default 5%).
            soft_deviation_threshold: Permissible fractional deviation from target area (default 25%).
        """
        self.hard_tolerance = hard_tolerance
        self.soft_deviation_threshold = soft_deviation_threshold

    def validate(
        self,
        geometry: Geometry,
        floor_plan_spec: Optional[FloorPlanSpec] = None,
        floor_reqs: Optional[FloorRequirements] = None,
    ) -> List[ValidationIssue]:
        """Validate usable areas of all rooms on a floor.

        Args:
            geometry: Floor Geometry.
            floor_plan_spec: Planning spec for this floor.
            floor_reqs: Requirements for this floor.

        Returns:
            List of ValidationIssue instances.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        # Build mapping of room_type -> target / min requirements
        min_areas: Dict[str, float] = {}
        target_areas: Dict[str, float] = {}

        if floor_plan_spec:
            for rs in floor_plan_spec.room_specs:
                if rs.min_area_sqm:
                    min_areas[rs.room_type] = rs.min_area_sqm
                if rs.target_area_sqm:
                    target_areas[rs.room_type] = rs.target_area_sqm
        elif floor_reqs:
            for rr in floor_reqs.room_requirements:
                if rr.min_area_sqm:
                    min_areas[rr.room_type] = rr.min_area_sqm
                target_val = getattr(rr, "preferred_area_sqm", None) or getattr(rr, "target_area_sqm", None)
                if target_val:
                    target_areas[rr.room_type] = target_val

        for room in geometry.rooms:
            if room.is_corridor:
                continue

            rtype = room.room_type
            actual_area = room.area_sqm

            # 1. Hard Minimum Area Check
            if rtype in min_areas:
                min_req = min_areas[rtype]
                min_allowed = min_req * (1.0 - self.hard_tolerance)
                if actual_area < min_allowed:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="dimension",
                            check="minimum_area",
                            message=(
                                f"Room '{rtype}' (id={room.id}) usable area {actual_area:.2f} sqm "
                                f"is below hard minimum required {min_req:.2f} sqm"
                            ),
                            details={
                                "actual_usable_area_sqm": actual_area,
                                "minimum_required_sqm": min_req,
                                "deficit_sqm": round(min_req - actual_area, 2),
                            },
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )

            # 2. Soft Target Area Deviation (Warning)
            if rtype in target_areas:
                target = target_areas[rtype]
                lower_warn = target * (1.0 - self.soft_deviation_threshold)
                upper_warn = target * (1.0 + self.soft_deviation_threshold)

                if actual_area < lower_warn:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="dimension",
                            check="target_area_undersize",
                            message=(
                                f"Room '{rtype}' (id={room.id}) usable area {actual_area:.2f} sqm "
                                f"is substantially below preferred target {target:.2f} sqm"
                            ),
                            details={"actual_area": actual_area, "target_area": target},
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
                elif actual_area > upper_warn:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="dimension",
                            check="target_area_oversize",
                            message=(
                                f"Room '{rtype}' (id={room.id}) usable area {actual_area:.2f} sqm "
                                f"is substantially above preferred target {target:.2f} sqm"
                            ),
                            details={"actual_area": actual_area, "target_area": target},
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )

        return issues
