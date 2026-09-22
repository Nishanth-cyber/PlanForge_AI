"""Room Validator for structural completeness, ASAA allocation containment, and geometric topology.

Independently checks:
- Structural completeness (no missing rooms, no invented rooms, count matching)
- Correct floor assignments
- ASAA allocated region containment and reference integrity
- Geometric topology (valid polygons, non-zero area, no self-intersections)
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set
from shapely.geometry import Polygon

from app.geometry.geometry_utils import to_shapely_polygon
from app.models.allocation import Allocation, AllocationSet
from app.models.architectural_design import ArchitecturalDesign, ArchitecturalDesignSet
from app.models.geometry import Geometry, GeoRoom
from app.models.planning import FloorPlanSpec, PlanningSpec
from app.models.requirements import FloorRequirements, Requirements
from app.models.validation import ValidationIssue


class RoomValidator:
    """Independently verifies room completeness, allocation containment, and topology."""

    def __init__(self, containment_tolerance: float = 0.05, max_spill_area_sqm: float = 0.05):
        """Initialize RoomValidator.

        Args:
            containment_tolerance: Buffer tolerance in meters for allocation containment.
            max_spill_area_sqm: Numerical area tolerance in square meters.
        """
        self.containment_tolerance = containment_tolerance
        self.max_spill_area_sqm = max_spill_area_sqm

    def validate_floor(
        self,
        geometry: Geometry,
        floor_reqs: Optional[FloorRequirements] = None,
        floor_plan_spec: Optional[FloorPlanSpec] = None,
        allocation: Optional[Allocation] = None,
        floor_design: Optional[ArchitecturalDesign] = None,
    ) -> List[ValidationIssue]:
        """Validate all rooms on a single floor.

        Args:
            geometry: Floor Geometry.
            floor_reqs: Upstream requirements for this floor (WHAT).
            floor_plan_spec: Upstream planning spec for this floor (STRATEGY).
            allocation: Upstream ASAA allocation for this floor (WHERE).
            floor_design: Upstream architectural design for this floor (HOW).

        Returns:
            List of ValidationIssue instances.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        habitable_rooms = [r for r in geometry.rooms if not r.is_corridor]

        # 1. Topology & Non-Degeneracy Checks
        for room in geometry.rooms:
            built_poly = room.built_polygon or room.usable_polygon
            usable_poly = room.usable_polygon or room.built_polygon

            # Check built polygon
            if not built_poly or len(built_poly) < 3:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="room_geometry",
                        check="valid_polygon",
                        message=f"Room '{room.room_type}' (id={room.id}) has fewer than 3 vertices",
                        target_id=room.id,
                        room_id=room.id,
                        floor_number=floor_num,
                    )
                )
                continue

            try:
                p = to_shapely_polygon(built_poly)
                if not p.is_valid:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="room_geometry",
                            check="polygon_topology",
                            message=f"Room '{room.room_type}' (id={room.id}) has self-intersecting or invalid polygon",
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
                if p.area <= 0.001:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="room_geometry",
                            check="positive_area",
                            message=f"Room '{room.room_type}' (id={room.id}) has zero or non-positive built area",
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
            except Exception as e:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="room_geometry",
                        check="polygon_creation",
                        message=f"Room '{room.room_type}' (id={room.id}) polygon error: {e}",
                        target_id=room.id,
                        room_id=room.id,
                        floor_number=floor_num,
                    )
                )

            # Check usable polygon
            if not usable_poly or len(usable_poly) < 3:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="room_geometry",
                        check="usable_polygon",
                        message=f"Room '{room.room_type}' (id={room.id}) has missing or invalid usable polygon",
                        target_id=room.id,
                        room_id=room.id,
                        floor_number=floor_num,
                    )
                )
            elif (room.area_sqm if room.area_sqm > 0 else (p.area if 'p' in locals() else 0)) <= 0:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="room_geometry",
                        check="positive_usable_area",
                        message=f"Room '{room.room_type}' (id={room.id}) has zero or non-positive usable area ({room.area_sqm} sqm)",
                        target_id=room.id,
                        room_id=room.id,
                        floor_number=floor_num,
                    )
                )

        # 2. Structural Completeness (Check Group 1)
        # Verify required rooms exist and no extra rooms are invented
        expected_room_types: List[str] = []
        if floor_plan_spec:
            for rs in floor_plan_spec.room_specs:
                expected_room_types.append(rs.room_type)
        elif floor_reqs:
            for rr in floor_reqs.room_requirements:
                expected_room_types.append(rr.room_type)

        if expected_room_types:
            actual_types = [r.room_type for r in habitable_rooms]

            # Check for missing rooms
            actual_type_counts: Dict[str, int] = {}
            for t in actual_types:
                actual_type_counts[t] = actual_type_counts.get(t, 0) + 1

            expected_type_counts: Dict[str, int] = {}
            for t in expected_room_types:
                expected_type_counts[t] = expected_type_counts.get(t, 0) + 1

            for exp_type, exp_cnt in expected_type_counts.items():
                act_cnt = actual_type_counts.get(exp_type, 0)
                if act_cnt < exp_cnt:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="completeness",
                            check="missing_room",
                            message=f"Floor {floor_num} is missing required room '{exp_type}' (expected {exp_cnt}, found {act_cnt})",
                            details={"room_type": exp_type, "expected_count": exp_cnt, "actual_count": act_cnt},
                            floor_number=floor_num,
                        )
                    )

            # Check for invented rooms
            for act_type, act_cnt in actual_type_counts.items():
                exp_cnt = expected_type_counts.get(act_type, 0)
                if act_cnt > exp_cnt:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="completeness",
                            check="invented_room",
                            message=f"Floor {floor_num} contains invented/extra room '{act_type}' (found {act_cnt}, expected {exp_cnt})",
                            details={"room_type": act_type, "expected_count": exp_cnt, "actual_count": act_cnt},
                            floor_number=floor_num,
                        )
                    )

        # 3. Floor Assignment Correctness
        for room in geometry.rooms:
            if room.floor_number != floor_num:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="completeness",
                        check="wrong_floor_assignment",
                        message=(
                            f"Room '{room.room_type}' (id={room.id}) is placed on Floor {floor_num} "
                            f"but claims floor_number={room.floor_number}"
                        ),
                        target_id=room.id,
                        room_id=room.id,
                        floor_number=floor_num,
                    )
                )

        # 4. ASAA Allocation Containment & Reference Integrity (Check Group 3)
        if allocation and floor_design:
            # Map room_design_id -> RoomDesign
            design_map = {rd.id: rd for rd in floor_design.rooms}

            for room in habitable_rooms:
                if not room.architectural_room_id:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="traceability",
                            check="missing_architectural_reference",
                            message=f"Room '{room.room_type}' (id={room.id}) has no architectural_room_id reference",
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
                    continue

                r_design = design_map.get(room.architectural_room_id)
                if not r_design:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="traceability",
                            check="unresolved_architectural_design",
                            message=(
                                f"Room '{room.room_type}' (id={room.id}) references unknown "
                                f"architectural design id '{room.architectural_room_id}'"
                            ),
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
                    continue

                if not r_design.allocated_region_id:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="allocation",
                            check="missing_allocation_reference",
                            message=(
                                f"RoomDesign '{r_design.room_type}' (id={r_design.id}) has no allocated_region_id"
                            ),
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
                    continue

                matched_region = allocation.get_region_by_id(r_design.allocated_region_id)
                if not matched_region:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="allocation",
                            check="unresolved_allocated_region",
                            message=(
                                f"Room '{room.room_type}' references non-existent allocated region "
                                f"id '{r_design.allocated_region_id}' on Floor {floor_num}"
                            ),
                            details={"allocated_region_id": r_design.allocated_region_id},
                            target_id=room.id,
                            room_id=room.id,
                            floor_number=floor_num,
                        )
                    )
                    continue

                # Independently verify physical containment in AllocatedRegion
                if matched_region.polygon and len(matched_region.polygon) >= 3:
                    reg_poly = to_shapely_polygon(matched_region.polygon)
                    if self.containment_tolerance > 0:
                        reg_poly = reg_poly.buffer(self.containment_tolerance)

                    room_poly = to_shapely_polygon(room.built_polygon)
                    if not (reg_poly.contains(room_poly) or reg_poly.covers(room_poly)):
                        spill = room_poly.difference(reg_poly)
                        if spill.area > self.max_spill_area_sqm:
                            issues.append(
                                ValidationIssue(
                                    severity="error",
                                    category="allocation",
                                    check="allocation_containment",
                                    message=(
                                        f"Room '{room.room_type}' (id={room.id}) extends outside its "
                                        f"assigned ASAA allocated region (id={matched_region.id}) by {spill.area:.2f} sqm"
                                    ),
                                    details={
                                        "allocated_region_id": matched_region.id,
                                        "spill_area_sqm": round(spill.area, 3),
                                    },
                                    target_id=room.id,
                                    room_id=room.id,
                                    floor_number=floor_num,
                                )
                            )

        return issues
