"""Window Validator for independent verification of exterior window openings.

Independently checks:
- Window references a valid GeoWall
- Window is placed strictly on an exterior wall (error if placed on interior partition)
- Window position lies on the wall segment
- Window dimensions and sill height are positive and fit the wall
- Compass orientation matching
"""

from __future__ import annotations
from typing import Dict, List, Optional
from shapely.geometry import LineString, Point, Polygon

from app.geometry.geometry_utils import (
    get_wall_orientation,
    segment_length,
    to_shapely_polygon,
)
from app.models.architectural_design import ArchitecturalDesign
from app.models.geometry import Geometry, GeoWall, GeoWindow
from app.models.validation import ValidationIssue
from app.models.windows import WindowIntent


class WindowValidator:
    """Independently verifies physical GeoWindow openings on exterior walls."""

    def __init__(self, wall_distance_tolerance: float = 0.15):
        """Initialize WindowValidator.

        Args:
            wall_distance_tolerance: Maximum allowed perpendicular distance from window point to wall line.
        """
        self.wall_distance_tolerance = wall_distance_tolerance

    def validate(
        self,
        geometry: Geometry,
        floor_design: Optional[ArchitecturalDesign] = None,
    ) -> List[ValidationIssue]:
        """Validate all windows on a single floor.

        Args:
            geometry: Floor Geometry containing walls and windows.
            floor_design: Upstream architectural design containing WindowIntents.

        Returns:
            List of ValidationIssue instances for any window violations.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        wall_map = {w.id: w for w in geometry.walls}
        room_map = {r.id: r for r in geometry.rooms}

        # Map intent_id -> WindowIntent if floor_design provided
        intent_map: Dict[str, WindowIntent] = {}
        if floor_design:
            for w_intent in floor_design.all_window_intents():
                intent_map[w_intent.id] = w_intent

        for window in geometry.windows:
            # 1. Dimension Sanity
            if window.width <= 0.1 or window.height <= 0.1:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="window",
                        check="window_dimensions",
                        message=f"Window (id={window.id}) has non-positive dimensions ({window.width}x{window.height})",
                        target_id=window.id,
                        floor_number=floor_num,
                    )
                )

            if window.sill_height < 0:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="window",
                        check="negative_sill_height",
                        message=f"Window (id={window.id}) has negative sill height ({window.sill_height}m)",
                        target_id=window.id,
                        floor_number=floor_num,
                    )
                )

            # 2. Wall Attachment Check (No Floating Windows)
            if not window.wall_id or window.wall_id not in wall_map:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="window",
                        check="floating_window",
                        message=f"Window (id={window.id}) is not attached to any valid wall (wall_id='{window.wall_id}')",
                        target_id=window.id,
                        floor_number=floor_num,
                    )
                )
                continue

            wall = wall_map[window.wall_id]

            # 3. Position on Wall Check
            win_pt = Point(window.position)
            wall_line = LineString([wall.start, wall.end])
            dist = wall_line.distance(win_pt)

            if dist > self.wall_distance_tolerance:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="window",
                        check="window_off_wall",
                        message=(
                            f"Window (id={window.id}) position {window.position} does not lie on its "
                            f"assigned wall (distance={dist:.2f}m > {self.wall_distance_tolerance}m)"
                        ),
                        details={"distance_to_wall": round(dist, 3)},
                        target_id=window.id,
                        floor_number=floor_num,
                    )
                )

            # 4. Strict Exterior Wall Check (No Windows on Interior Partitions)
            if wall.type != "exterior":
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="window",
                        check="window_on_interior_wall",
                        message=(
                            f"Window (id={window.id}) is placed on an interior partition wall "
                            f"(id={wall.id}, type='{wall.type}')"
                        ),
                        details={"wall_id": wall.id, "wall_type": wall.type},
                        target_id=window.id,
                        floor_number=floor_num,
                    )
                )

            # 5. Wall Width vs Window Width
            w_len = segment_length((wall.start, wall.end))
            if w_len < window.width - 0.05:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="window",
                        check="wall_too_narrow_for_window",
                        message=(
                            f"Wall (id={wall.id}, length={w_len:.2f}m) is too narrow for window "
                            f"width {window.width:.2f}m"
                        ),
                        details={"wall_length": round(w_len, 2), "window_width": window.width},
                        target_id=window.id,
                        floor_number=floor_num,
                    )
                )

            # 6. Orientation Preference Check
            if window.intent_id and window.intent_id in intent_map:
                w_intent = intent_map[window.intent_id]
                if w_intent.wall_orientation:
                    expected_orient = w_intent.wall_orientation.lower().strip()
                    actual_orient = get_wall_orientation((wall.start, wall.end))
                    if actual_orient != expected_orient:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                category="window",
                                check="window_orientation_mismatch",
                                message=(
                                    f"Window (id={window.id}) faces '{actual_orient}' instead of "
                                    f"requested '{expected_orient}'"
                                ),
                                details={"expected_orientation": expected_orient, "actual_orientation": actual_orient},
                                target_id=window.id,
                                floor_number=floor_num,
                            )
                        )

        return issues
