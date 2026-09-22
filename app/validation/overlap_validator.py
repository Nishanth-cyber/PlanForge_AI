"""Overlap Validator for detecting physical room and zone collisions.

Independently checks pairwise 2D polygon intersections between all rooms, corridors,
and vertical cores, distinguishing legal shared-boundary contact from prohibited area overlaps.
"""

from __future__ import annotations
from typing import List, Tuple
from shapely.geometry import Polygon

from app.geometry.geometry_utils import to_shapely_polygon
from app.models.geometry import Geometry, GeoRoom
from app.models.validation import ValidationIssue


class OverlapValidator:
    """Independently verifies zero room area overlaps on a floor."""

    def __init__(self, max_allowed_overlap_sqm: float = 0.05):
        """Initialize OverlapValidator.

        Args:
            max_allowed_overlap_sqm: Maximum permissible intersection area before triggering an error.
        """
        self.max_allowed_overlap_sqm = max_allowed_overlap_sqm

    def validate(self, geometry: Geometry) -> List[ValidationIssue]:
        """Validate that no two rooms or circulation zones overlap in area.

        Args:
            geometry: Floor Geometry to inspect.

        Returns:
            List of ValidationIssue instances for any overlapping room pairs.
        """
        issues: List[ValidationIssue] = []
        rooms = geometry.rooms
        n = len(rooms)

        # 1. Pairwise room check
        for i in range(n):
            r1 = rooms[i]
            if not r1.built_polygon or len(r1.built_polygon) < 3:
                continue
            poly1 = to_shapely_polygon(r1.built_polygon)

            for j in range(i + 1, n):
                r2 = rooms[j]
                if not r2.built_polygon or len(r2.built_polygon) < 3:
                    continue
                poly2 = to_shapely_polygon(r2.built_polygon)

                if poly1.intersects(poly2):
                    inter = poly1.intersection(poly2)
                    inter_area = float(inter.area) if hasattr(inter, "area") else 0.0
                    if inter_area > self.max_allowed_overlap_sqm:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="overlap",
                                check="room_overlap",
                                message=(
                                    f"Room '{r1.room_type}' (id={r1.id}) overlaps with "
                                    f"Room '{r2.room_type}' (id={r2.id}) by {inter_area:.2f} sqm"
                                ),
                                details={
                                    "room_1_id": r1.id,
                                    "room_1_type": r1.room_type,
                                    "room_2_id": r2.id,
                                    "room_2_type": r2.room_type,
                                    "overlap_area_sqm": round(inter_area, 3),
                                },
                                target_id=r1.id,
                                room_id=r1.id,
                                floor_number=geometry.floor_number,
                            )
                        )

        # 2. Check staircase vs habitable rooms
        for stair in geometry.staircases:
            if not stair.polygon or len(stair.polygon) < 3:
                continue
            stair_poly = to_shapely_polygon(stair.polygon)

            for room in rooms:
                if room.is_corridor:
                    continue  # Staircase touching/accessing corridor is expected
                if not room.built_polygon or len(room.built_polygon) < 3:
                    continue
                room_poly = to_shapely_polygon(room.built_polygon)

                if stair_poly.intersects(room_poly):
                    inter = stair_poly.intersection(room_poly)
                    inter_area = float(inter.area) if hasattr(inter, "area") else 0.0
                    if inter_area > self.max_allowed_overlap_sqm:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="overlap",
                                check="staircase_room_overlap",
                                message=(
                                    f"Staircase (id={stair.id}) overlaps with "
                                    f"Room '{room.room_type}' (id={room.id}) by {inter_area:.2f} sqm"
                                ),
                                details={
                                    "staircase_id": stair.id,
                                    "room_id": room.id,
                                    "overlap_area_sqm": round(inter_area, 3),
                                },
                                target_id=stair.id,
                                room_id=room.id,
                                floor_number=geometry.floor_number,
                            )
                        )

        return issues
