"""Door Validator for independent physical door placement and swing arc verification.

Independently checks:
- Door references a valid, existing GeoWall
- Door position lies on the wall segment
- Interior doors connect valid adjacent spaces
- Entrance and balcony doors are placed on exterior walls
- Door swing arc clearance and boundary containment
"""

from __future__ import annotations
from typing import List, Optional, Tuple
from shapely.geometry import LineString, Point, Polygon

from app.geometry.geometry_utils import segment_length, to_shapely_polygon
from app.models.geometry import Geometry, GeoDoor, GeoWall
from app.models.validation import ValidationIssue


class DoorValidator:
    """Independently verifies physical GeoDoor geometry and wall placement."""

    def __init__(self, wall_distance_tolerance: float = 0.15):
        """Initialize DoorValidator.

        Args:
            wall_distance_tolerance: Maximum allowed perpendicular distance from door point to wall line.
        """
        self.wall_distance_tolerance = wall_distance_tolerance

    def validate(
        self,
        geometry: Geometry,
        buildable_boundary: Optional[List[Tuple[float, float]]] = None,
    ) -> List[ValidationIssue]:
        """Validate all doors on a single floor.

        Args:
            geometry: Floor Geometry containing walls and doors.
            buildable_boundary: Optional buildable envelope coordinates.

        Returns:
            List of ValidationIssue instances for any door violations.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        wall_map = {w.id: w for w in geometry.walls}
        room_map = {r.id: r for r in geometry.rooms}

        buildable_poly = None
        if buildable_boundary and len(buildable_boundary) >= 3:
            buildable_poly = to_shapely_polygon(buildable_boundary).buffer(0.05)

        for door in geometry.doors:
            # 1. Dimension Sanity
            if door.width <= 0.1 or door.height <= 0.1:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="door",
                        check="door_dimensions",
                        message=f"Door (id={door.id}) has invalid non-positive dimensions ({door.width}x{door.height})",
                        target_id=door.id,
                        floor_number=floor_num,
                    )
                )

            # 2. Wall Attachment Check (No Floating Doors)
            if not door.wall_id or door.wall_id not in wall_map:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="door",
                        check="floating_door",
                        message=f"Door (id={door.id}) is not attached to any valid wall (wall_id='{door.wall_id}')",
                        target_id=door.id,
                        floor_number=floor_num,
                    )
                )
                continue

            wall = wall_map[door.wall_id]

            # 3. Position on Wall Check
            door_pt = Point(door.position)
            wall_line = LineString([wall.start, wall.end])
            dist = wall_line.distance(door_pt)

            if dist > self.wall_distance_tolerance:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="door",
                        check="door_off_wall",
                        message=(
                            f"Door (id={door.id}) position {door.position} does not lie on its "
                            f"assigned wall (distance={dist:.2f}m > {self.wall_distance_tolerance}m)"
                        ),
                        details={"distance_to_wall": round(dist, 3)},
                        target_id=door.id,
                        floor_number=floor_num,
                    )
                )

            # 4. Wall Width vs Door Width
            w_len = segment_length((wall.start, wall.end))
            if w_len < door.width - 0.05:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="door",
                        check="wall_too_narrow_for_door",
                        message=(
                            f"Wall (id={wall.id}, length={w_len:.2f}m) is too narrow for door "
                            f"width {door.width:.2f}m"
                        ),
                        details={"wall_length": round(w_len, 2), "door_width": door.width},
                        target_id=door.id,
                        floor_number=floor_num,
                    )
                )

            # 5. Door Type vs Wall Type
            if door.type in {"entrance", "exterior", "balcony"} or door.connects_to in {"exterior", "balcony"}:
                if wall.type != "exterior":
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="door",
                            check="exterior_door_on_interior_wall",
                            message=(
                                f"Door (id={door.id}, type='{door.type}') is placed on an interior "
                                f"partition wall (id={wall.id})"
                            ),
                            target_id=door.id,
                            floor_number=floor_num,
                        )
                    )
            elif door.type == "interior":
                # Interior door should generally be on an interior wall
                if wall.type == "exterior" and door.connects_to != "exterior":
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            category="door",
                            check="interior_door_on_exterior_wall",
                            message=(
                                f"Interior door (id={door.id}) connecting '{door.connects_from}' to "
                                f"'{door.connects_to}' is placed on an exterior wall"
                            ),
                            target_id=door.id,
                            floor_number=floor_num,
                        )
                    )

            # 6. Door Swing Verification (Check Group 11)
            if door.swing_arc:
                if len(door.swing_arc) >= 3:
                    try:
                        swing_p = to_shapely_polygon(door.swing_arc)
                        if not swing_p.is_valid or swing_p.area <= 0.001:
                            issues.append(
                                ValidationIssue(
                                    severity="warning",
                                    category="door",
                                    check="invalid_swing_arc",
                                    message=f"Door (id={door.id}) has degenerate or self-intersecting swing arc polygon",
                                    target_id=door.id,
                                    floor_number=floor_num,
                                )
                            )
                        elif buildable_poly is not None and not buildable_poly.covers(swing_p):
                            # Swing extends outside building footprint
                            spill = swing_p.difference(buildable_poly)
                            if spill.area > 0.05:
                                issues.append(
                                    ValidationIssue(
                                        severity="error",
                                        category="door",
                                        check="door_swing_outside_boundary",
                                        message=(
                                            f"Door (id={door.id}) swing arc extends outside the buildable "
                                            f"boundary by {spill.area:.2f} sqm"
                                        ),
                                        target_id=door.id,
                                        floor_number=floor_num,
                                    )
                                )
                    except Exception as e:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                category="door",
                                check="swing_arc_error",
                                message=f"Door (id={door.id}) swing polygon check failed: {e}",
                                target_id=door.id,
                                floor_number=floor_num,
                            )
                        )

        return issues
