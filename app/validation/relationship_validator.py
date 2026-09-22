"""Relationship Validator for independent verification of functional spatial relationships.

Evaluates:
- Hard user-required adjacencies (shared wall or connecting door required)
- Soft planning-preferred adjacencies (warning if unfulfilled)
- Hard separation / avoid constraints (error if rooms touch or directly connect)
- Hard attached suite relationships (e.g. Master Bedroom + Attached Bathroom)
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple
from shapely.geometry import LineString

from app.geometry.geometry_utils import (
    find_shared_wall_segment,
    segment_length,
    to_shapely_polygon,
)
from app.models.geometry import Geometry, GeoRoom
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.requirements import FloorRequirements, Requirements
from app.models.validation import ValidationIssue


class RelationshipValidator:
    """Independently verifies spatial relationships against actual constructed geometry."""

    def __init__(self, min_shared_boundary_m: float = 0.3):
        """Initialize RelationshipValidator.

        Args:
            min_shared_boundary_m: Minimum shared wall segment length to count as physical contact.
        """
        self.min_shared_boundary_m = min_shared_boundary_m

    def validate(
        self,
        geometry: Geometry,
        floor_plan_spec: Optional[FloorPlanSpec] = None,
        floor_reqs: Optional[FloorRequirements] = None,
    ) -> List[ValidationIssue]:
        """Validate all spatial relationships on a single floor.

        Args:
            geometry: Floor Geometry containing rooms, walls, doors.
            floor_plan_spec: Planning spec for this floor.
            floor_reqs: User requirements for this floor.

        Returns:
            List of ValidationIssue instances for failed relationships.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        rooms = [r for r in geometry.rooms if not r.is_corridor]
        room_by_type: Dict[str, List[GeoRoom]] = {}
        room_by_id: Dict[str, GeoRoom] = {}
        for r in rooms:
            room_by_type.setdefault(r.room_type, []).append(r)
            room_by_id[r.id] = r

        # Helper: check physical contact or direct door between two rooms
        def are_physically_connected(r1: GeoRoom, r2: GeoRoom) -> Tuple[bool, str]:
            # 1. Check direct door connecting them
            for d_id in r1.doors:
                door = geometry.get_door(d_id)
                if door:
                    if (
                        door.connects_from in {r1.id, r1.room_type, r1.architectural_room_id}
                        and door.connects_to in {r2.id, r2.room_type, r2.architectural_room_id}
                    ) or (
                        door.connects_from in {r2.id, r2.room_type, r2.architectural_room_id}
                        and door.connects_to in {r1.id, r1.room_type, r1.architectural_room_id}
                    ):
                        return True, "connecting_door"

            # 2. Check shared wall boundary
            shared_seg = find_shared_wall_segment(
                r1.built_polygon,
                r2.built_polygon,
                min_length=self.min_shared_boundary_m,
            )
            if shared_seg is not None:
                return True, f"shared_wall ({segment_length(shared_seg):.2f}m)"

            return False, "no_contact"

        # 1. Hard User-Required Adjacency (Check Group 6)
        user_required_pairs: Set[Tuple[str, str]] = set()
        if floor_reqs:
            for rr in floor_reqs.room_requirements:
                for adj_target in rr.adjacency:
                    pair = tuple(sorted([rr.room_type, adj_target]))
                    user_required_pairs.add(pair)

        # Also from planning spec room specs with high priority or required links
        if floor_plan_spec:
            for rs in floor_plan_spec.room_specs:
                if rs.priority == "high":
                    for adj_target in rs.adjacency:
                        pair = tuple(sorted([rs.room_type, adj_target]))
                        user_required_pairs.add(pair)

        for type_a, type_b in user_required_pairs:
            rooms_a = room_by_type.get(type_a, [])
            rooms_b = room_by_type.get(type_b, [])

            if not rooms_a or not rooms_b:
                continue  # Missing rooms are handled by RoomValidator

            # Check if any room of type A connects with any room of type B
            connected = False
            for ra in rooms_a:
                for rb in rooms_b:
                    is_conn, reason = are_physically_connected(ra, rb)
                    if is_conn:
                        connected = True
                        break
                if connected:
                    break

            if not connected:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="relationship",
                        check="required_adjacency",
                        message=(
                            f"Required adjacency between '{type_a}' and '{type_b}' is not physically "
                            f"realized on Floor {floor_num} (no shared wall >= {self.min_shared_boundary_m}m or direct door)"
                        ),
                        details={"room_type_1": type_a, "room_type_2": type_b, "relationship": "required_adjacency"},
                        floor_number=floor_num,
                    )
                )

        # 2. Soft Planning-Preferred Adjacency (Check Group 7 - Warnings)
        planning_preferred_pairs: Set[Tuple[str, str]] = set()
        if floor_plan_spec:
            for src_type, targets in floor_plan_spec.adjacency_matrix.items():
                for tgt_type in targets:
                    pair = tuple(sorted([src_type, tgt_type]))
                    if pair not in user_required_pairs:
                        planning_preferred_pairs.add(pair)

        for type_a, type_b in planning_preferred_pairs:
            rooms_a = room_by_type.get(type_a, [])
            rooms_b = room_by_type.get(type_b, [])

            if not rooms_a or not rooms_b:
                continue

            connected = False
            for ra in rooms_a:
                for rb in rooms_b:
                    is_conn, _ = are_physically_connected(ra, rb)
                    if is_conn:
                        connected = True
                        break
                if connected:
                    break

            if not connected:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        category="relationship",
                        check="preferred_adjacency",
                        message=(
                            f"Preferred adjacency between '{type_a}' and '{type_b}' is not realized "
                            f"on Floor {floor_num}"
                        ),
                        details={"room_type_1": type_a, "room_type_2": type_b, "relationship": "preferred_adjacency"},
                        floor_number=floor_num,
                    )
                )

        # 3. Hard Separation / Avoid Constraints (Check Group 8)
        avoid_pairs: Set[Tuple[str, str]] = set()
        if floor_plan_spec:
            for src_type, targets in floor_plan_spec.avoid_matrix.items():
                for tgt_type in targets:
                    avoid_pairs.add(tuple(sorted([src_type, tgt_type])))
        elif floor_reqs:
            for rr in floor_reqs.room_requirements:
                for sep_target in rr.separation:
                    avoid_pairs.add(tuple(sorted([rr.room_type, sep_target])))

        for type_a, type_b in avoid_pairs:
            rooms_a = room_by_type.get(type_a, [])
            rooms_b = room_by_type.get(type_b, [])

            for ra in rooms_a:
                for rb in rooms_b:
                    is_conn, reason = are_physically_connected(ra, rb)
                    if is_conn:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="relationship",
                                check="separation_violation",
                                message=(
                                    f"Separation violation: Room '{type_a}' (id={ra.id}) touches or connects "
                                    f"to Room '{type_b}' (id={rb.id}) via {reason}"
                                ),
                                details={
                                    "room_1_id": ra.id,
                                    "room_2_id": rb.id,
                                    "observed_connection": reason,
                                },
                                target_id=ra.id,
                                room_id=ra.id,
                                floor_number=floor_num,
                            )
                        )

        # 4. Attached Room Relationships (Check Group 9)
        if floor_plan_spec:
            for rs in floor_plan_spec.room_specs:
                if rs.attached_to_room_id:
                    # rs is an attached space (e.g. ensuite bathroom)
                    child_rooms = room_by_type.get(rs.room_type, [])
                    # Parent room can be resolved by room_spec_id
                    parent_rooms = [
                        r for r in rooms
                        if r.room_type in {"master_bedroom", "bedroom", "suite"}
                    ]
                    attached = False
                    for cr in child_rooms:
                        for pr in parent_rooms:
                            is_conn, _ = are_physically_connected(cr, pr)
                            if is_conn:
                                attached = True
                                break
                        if attached:
                            break

                    if not attached:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="relationship",
                                check="attached_suite_connection",
                                message=(
                                    f"Attached room '{rs.room_type}' is not physically connected or adjacent "
                                    f"to its parent room on Floor {floor_num}"
                                ),
                                details={"attached_room_type": rs.room_type},
                                floor_number=floor_num,
                            )
                        )

        return issues
