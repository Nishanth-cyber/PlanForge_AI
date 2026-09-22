"""Circulation Validator for corridor network integrity and multi-floor circulation consistency.

Independently checks:
- Corridor accessibility and connectivity to bordering spaces
- Multi-floor floor count matching against requirements
- Inter-floor circulation pathway consistency
"""

from __future__ import annotations
from typing import List, Optional

from app.models.floor_plan import FloorPlanSet
from app.models.geometry import Geometry, GeoRoom
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue


class CirculationValidator:
    """Independently verifies corridor circulation and multi-floor consistency."""

    def validate_corridors(self, geometry: Geometry) -> List[ValidationIssue]:
        """Validate corridor geometry and door connections on a floor.

        Args:
            geometry: Floor Geometry.

        Returns:
            List of ValidationIssue instances for circulation defects.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        corridors = [r for r in geometry.rooms if r.is_corridor]
        if not corridors:
            return issues

        for corridor in corridors:
            # Corridors should have at least one door connection
            if not corridor.doors:
                # Check if any door in geometry connects to this corridor
                has_door = False
                for d in geometry.doors:
                    if d.connects_from in {corridor.id, "circulation"} or d.connects_to in {corridor.id, "circulation"}:
                        has_door = True
                        break

                if not has_door:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="circulation",
                            check="disconnected_corridor",
                            message=f"Circulation corridor (id={corridor.id}) on Floor {floor_num} has no connected doorways",
                            target_id=corridor.id,
                            room_id=corridor.id,
                            floor_number=floor_num,
                        )
                    )

        return issues

    def validate_multi_floor_consistency(
        self,
        floor_plan_set: FloorPlanSet,
        requirements: Optional[Requirements] = None,
    ) -> List[ValidationIssue]:
        """Validate multi-floor structure against requirements.

        Args:
            floor_plan_set: Complete FloorPlanSet.
            requirements: Upstream Requirements.

        Returns:
            List of ValidationIssue instances.
        """
        issues: List[ValidationIssue] = []

        actual_floors = {fp.floor_number for fp in floor_plan_set.floor_plans}
        expected_floor_count = len(actual_floors)
        if requirements:
            expected_floor_count = requirements.target_floors

        # 1. Floor count match
        if len(actual_floors) != expected_floor_count:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="multi_floor",
                    check="floor_count_mismatch",
                    message=(
                        f"FloorPlanSet contains {len(actual_floors)} floors ({sorted(actual_floors)}), "
                        f"but requirements specified {expected_floor_count} floors"
                    ),
                    details={"expected_floors": expected_floor_count, "actual_floors": list(actual_floors)},
                )
            )

        # 2. Multi-floor vertical circulation requirement
        if len(actual_floors) >= 2:
            for fp in floor_plan_set.floor_plans:
                if not fp.geometry or not fp.geometry.staircases:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="multi_floor",
                            check="missing_multi_floor_staircase",
                            message=f"Multi-floor building requires vertical core on Floor {fp.floor_number}, none found",
                            floor_number=fp.floor_number,
                        )
                    )

        return issues
