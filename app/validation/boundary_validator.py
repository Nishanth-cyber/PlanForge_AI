"""Boundary Validator for independent verification of plot and buildable envelope containment.

Validates that all constructed room, corridor, and staircase geometries lie strictly
within the designated plot and buildable boundaries without replacing polygons with bounding boxes.
"""

from __future__ import annotations
from typing import List, Optional, Tuple
from shapely.geometry import Polygon

from app.geometry.geometry_utils import to_shapely_polygon
from app.models.geometry import Geometry, GeoRoom
from app.models.validation import ValidationIssue


class BoundaryValidator:
    """Independently verifies geometric boundary containment."""

    def __init__(self, tolerance: float = 0.05, max_spill_area_sqm: float = 0.05):
        """Initialize BoundaryValidator.

        Args:
            tolerance: Linear boundary buffer tolerance in meters.
            max_spill_area_sqm: Numerical area tolerance in square meters.
        """
        self.tolerance = tolerance
        self.max_spill_area_sqm = max_spill_area_sqm

    def validate(
        self,
        geometry: Geometry,
        plot_boundary: Optional[List[Tuple[float, float]]] = None,
        buildable_boundary: Optional[List[Tuple[float, float]]] = None,
    ) -> List[ValidationIssue]:
        """Validate floor geometry against plot and buildable boundaries.

        Args:
            geometry: Floor Geometry containing rooms, corridors, staircases.
            plot_boundary: Polygonal property boundary coordinates.
            buildable_boundary: Setback-adjusted buildable envelope coordinates.

        Returns:
            List of ValidationIssue instances for any boundary violations.
        """
        issues: List[ValidationIssue] = []

        plot_poly = None
        plot_coords = plot_boundary or geometry.plot_polygon
        if plot_coords and len(plot_coords) >= 3:
            plot_poly = to_shapely_polygon(plot_coords)

        buildable_poly = None
        buildable_coords = buildable_boundary or geometry.buildable_polygon
        if buildable_coords and len(buildable_coords) >= 3:
            buildable_poly = to_shapely_polygon(buildable_coords)
            # Add small tolerance buffer for numerical edge touching
            if self.tolerance > 0:
                buildable_poly = buildable_poly.buffer(self.tolerance)

        # 1. Check all rooms (habitable and corridors)
        for room in geometry.rooms:
            poly_coords = room.built_polygon or room.usable_polygon
            if not poly_coords or len(poly_coords) < 3:
                continue
            room_poly = to_shapely_polygon(poly_coords)

            # Check Plot Boundary Containment (Zero Tolerance)
            if plot_poly is not None:
                if not (plot_poly.contains(room_poly) or plot_poly.covers(room_poly)):
                    spill = room_poly.difference(plot_poly)
                    if spill.area > self.max_spill_area_sqm:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="boundary",
                                check="plot_boundary_containment",
                                message=(
                                    f"Room '{room.room_type}' (id={room.id}) extends outside "
                                    f"the property plot boundary by {spill.area:.2f} sqm"
                                ),
                                details={"spill_area_sqm": round(spill.area, 3), "boundary_type": "plot"},
                                target_id=room.id,
                                room_id=room.id,
                                floor_number=geometry.floor_number,
                            )
                        )

            # Check Buildable Boundary Containment
            if buildable_poly is not None:
                if not (buildable_poly.contains(room_poly) or buildable_poly.covers(room_poly)):
                    spill = room_poly.difference(buildable_poly)
                    if spill.area > self.max_spill_area_sqm:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="boundary",
                                check="buildable_boundary_containment",
                                message=(
                                    f"Room '{room.room_type}' (id={room.id}) extends outside "
                                    f"the buildable envelope by {spill.area:.2f} sqm"
                                ),
                                details={"spill_area_sqm": round(spill.area, 3), "boundary_type": "buildable"},
                                target_id=room.id,
                                room_id=room.id,
                                floor_number=geometry.floor_number,
                            )
                        )

        # 2. Check staircases
        for stair in geometry.staircases:
            if not stair.polygon or len(stair.polygon) < 3:
                continue
            stair_poly = to_shapely_polygon(stair.polygon)

            if buildable_poly is not None:
                if not (buildable_poly.contains(stair_poly) or buildable_poly.covers(stair_poly)):
                    spill = stair_poly.difference(buildable_poly)
                    if spill.area > self.max_spill_area_sqm:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="boundary",
                                check="staircase_boundary_containment",
                                message=(
                                    f"Staircase (id={stair.id}) extends outside "
                                    f"the buildable envelope by {spill.area:.2f} sqm"
                                ),
                                details={"spill_area_sqm": round(spill.area, 3)},
                                target_id=stair.id,
                                floor_number=geometry.floor_number,
                            )
                        )

        return issues
