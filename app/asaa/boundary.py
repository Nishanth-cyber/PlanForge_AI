"""Buildable boundary calculator for ASAA.

Distinguishes between PLOT BOUNDARY and BUILDABLE BOUNDARY.
Computes setbacks for rectangular, L-shaped, and irregular polygon plots
without silently replacing irregular polygons with bounding boxes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple
from shapely.geometry import Polygon, MultiPolygon
from app.asaa.exceptions import BoundaryConstraintError
from app.geometry.geometry_utils import extract_largest_polygon


@dataclass
class BuildableBoundary:
    """Represents the derived buildable boundary within a plot."""
    polygon: list[Tuple[float, float]]
    area_sqm: float
    bounds: Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)
    is_rectangular: bool
    shapely_polygon: Polygon
    plot_polygon: list[Tuple[float, float]] = field(default_factory=list)
    setbacks: dict[str, float] = field(default_factory=dict)


class BuildableBoundaryCalculator:
    """Calculates the buildable boundary from plot boundaries and setbacks."""

    @staticmethod
    def calculate(
        plot_polygon: Optional[list[Tuple[float, float]]] = None,
        plot_area_sqm: Optional[float] = None,
        plot_width_m: Optional[float] = None,
        plot_depth_m: Optional[float] = None,
        setbacks: Optional[dict[str, Any]] = None,
    ) -> BuildableBoundary:
        """Calculate the buildable boundary.

        Args:
            plot_polygon: Explicit list of (x, y) coordinates defining plot boundary.
            plot_area_sqm: Plot area if polygon is not explicitly provided.
            plot_width_m: Plot width in meters.
            plot_depth_m: Plot depth in meters.
            setbacks: Dictionary of setbacks (e.g. {"front": 3.0, "rear": 2.0, "left": 1.5, "right": 1.5}).

        Returns:
            BuildableBoundary object.

        Raises:
            BoundaryConstraintError: If plot geometry is invalid or buildable area is zero/negative.
        """
        # 1. Derive base plot polygon
        poly_points = BuildableBoundaryCalculator._derive_plot_polygon(
            plot_polygon, plot_area_sqm, plot_width_m, plot_depth_m
        )

        if len(poly_points) < 3:
            raise BoundaryConstraintError(
                "Plot boundary must have at least 3 vertices",
                plot_polygon=poly_points,
            )

        base_shapely = Polygon(poly_points)
        if not base_shapely.is_valid:
            base_shapely = base_shapely.buffer(0)
            if not base_shapely.is_valid or base_shapely.is_empty:
                raise BoundaryConstraintError(
                    "Plot boundary polygon is self-intersecting or geometrically invalid",
                    plot_polygon=poly_points,
                )

        if base_shapely.area <= 0:
            raise BoundaryConstraintError(
                f"Plot boundary area must be positive, got {base_shapely.area}",
                plot_polygon=poly_points,
            )

        # 2. Extract setbacks
        norm_setbacks = BuildableBoundaryCalculator._normalize_setbacks(setbacks)

        # 3. If no setbacks, buildable boundary = plot boundary
        if not norm_setbacks or all(v <= 0 for v in norm_setbacks.values()):
            coords = [(float(x), float(y)) for x, y in base_shapely.exterior.coords[:-1]]
            min_x, min_y, max_x, max_y = base_shapely.bounds
            is_rect = BuildableBoundaryCalculator._check_is_rectangular(coords)
            return BuildableBoundary(
                polygon=coords,
                area_sqm=base_shapely.area,
                bounds=(min_x, min_y, max_x, max_y),
                is_rectangular=is_rect,
                shapely_polygon=base_shapely,
                plot_polygon=poly_points,
                setbacks=norm_setbacks,
            )

        # 4. Apply setbacks
        is_axis_aligned_rect = BuildableBoundaryCalculator._is_axis_aligned_rectangle(poly_points)

        if is_axis_aligned_rect:
            buildable_shapely = BuildableBoundaryCalculator._apply_rect_setbacks(
                poly_points, norm_setbacks
            )
        else:
            buildable_shapely = BuildableBoundaryCalculator._apply_polygon_setbacks(
                base_shapely, norm_setbacks
            )

        if buildable_shapely.is_empty or buildable_shapely.area <= 0:
            raise BoundaryConstraintError(
                f"Setbacks {norm_setbacks} eliminate entire buildable area of plot (plot area: {base_shapely.area:.1f} m²)",
                plot_polygon=poly_points,
            )

        # In case of MultiPolygon or GeometryCollection (e.g. irregular polygon split by buffer/clip), keep largest component
        buildable_shapely = extract_largest_polygon(buildable_shapely)

        coords = [(round(float(x), 4), round(float(y), 4)) for x, y in buildable_shapely.exterior.coords[:-1]]
        min_x, min_y, max_x, max_y = buildable_shapely.bounds
        is_rect = BuildableBoundaryCalculator._check_is_rectangular(coords)

        return BuildableBoundary(
            polygon=coords,
            area_sqm=round(buildable_shapely.area, 4),
            bounds=(round(min_x, 4), round(min_y, 4), round(max_x, 4), round(max_y, 4)),
            is_rectangular=is_rect,
            shapely_polygon=buildable_shapely,
            plot_polygon=poly_points,
            setbacks=norm_setbacks,
        )

    @staticmethod
    def _derive_plot_polygon(
        plot_polygon: Optional[list[Tuple[float, float]]],
        plot_area_sqm: Optional[float],
        plot_width_m: Optional[float],
        plot_depth_m: Optional[float],
    ) -> list[Tuple[float, float]]:
        """Derive vertices for the plot boundary."""
        if plot_polygon and len(plot_polygon) >= 3:
            # Drop duplicate trailing closure vertex if present
            if plot_polygon[0] == plot_polygon[-1] and len(plot_polygon) > 3:
                return [(float(x), float(y)) for x, y in plot_polygon[:-1]]
            return [(float(x), float(y)) for x, y in plot_polygon]

        # Use width and depth if available
        if plot_width_m and plot_depth_m and plot_width_m > 0 and plot_depth_m > 0:
            w, d = float(plot_width_m), float(plot_depth_m)
            return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]

        # If only area is given, default to 1.5:1 rectangle
        area = float(plot_area_sqm) if plot_area_sqm and plot_area_sqm > 0 else 200.0
        aspect = 1.5
        w = (area * aspect) ** 0.5
        d = area / w
        return [(0.0, 0.0), (round(w, 2), 0.0), (round(w, 2), round(d, 2)), (0.0, round(d, 2))]

    @staticmethod
    def _normalize_setbacks(setbacks: Optional[dict[str, Any]]) -> dict[str, float]:
        """Normalize setbacks to standard front/rear/left/right/side floats."""
        if not setbacks:
            return {}

        result: dict[str, float] = {}
        if "all" in setbacks:
            val = max(0.0, float(setbacks["all"]))
            return {"front": val, "rear": val, "left": val, "right": val, "side": val}

        # Side setback applies to both left and right if not individually specified (Task 3 & 4)
        side_val = float(setbacks["side"]) if ("side" in setbacks and setbacks["side"] is not None) else None

        for side in ("front", "rear", "left", "right"):
            if side in setbacks and setbacks[side] is not None:
                result[side] = max(0.0, float(setbacks[side]))
            elif side in ("left", "right") and side_val is not None:
                result[side] = max(0.0, side_val)
            else:
                result[side] = 0.0

        if side_val is not None:
            result["side"] = max(0.0, side_val)
        elif result.get("left") == result.get("right") and result.get("left", 0.0) > 0:
            result["side"] = result["left"]

        return result

    @staticmethod
    def _is_axis_aligned_rectangle(points: list[Tuple[float, float]]) -> bool:
        """Check if polygon is an axis-aligned rectangle with 4 vertices."""
        if len(points) != 4:
            return False
        xs = sorted(set(round(p[0], 3) for p in points))
        ys = sorted(set(round(p[1], 3) for p in points))
        return len(xs) == 2 and len(ys) == 2

    @staticmethod
    def _apply_rect_setbacks(
        points: list[Tuple[float, float]], setbacks: dict[str, float]
    ) -> Polygon:
        """Apply directional setbacks to an axis-aligned rectangular plot."""
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Standard architectural convention:
        # front is typically min_y (or entrance facing), rear is max_y
        left_s = setbacks.get("left", 0.0)
        right_s = setbacks.get("right", 0.0)
        front_s = setbacks.get("front", 0.0)
        rear_s = setbacks.get("rear", 0.0)

        new_min_x = min_x + left_s
        new_max_x = max_x - right_s
        new_min_y = min_y + front_s
        new_max_y = max_y - rear_s

        if new_max_x <= new_min_x or new_max_y <= new_min_y:
            return Polygon()

        return Polygon([
            (new_min_x, new_min_y),
            (new_max_x, new_min_y),
            (new_max_x, new_max_y),
            (new_min_x, new_max_y),
        ])

    @staticmethod
    def _apply_polygon_setbacks(
        shapely_poly: Polygon, setbacks: dict[str, float]
    ) -> Polygon:
        """Apply setbacks to an irregular or L-shaped polygon.
        
        Preserves polygon boundary shape and does NOT convert to bounding box.
        """
        # If setbacks are uniform
        vals = list(setbacks.values())
        if vals and all(abs(v - vals[0]) < 1e-4 for v in vals):
            uniform_sb = vals[0]
            if uniform_sb <= 0:
                return shapely_poly
            buffered = shapely_poly.buffer(-uniform_sb, join_style="mitre")
            return extract_largest_polygon(buffered)

        # Directional setbacks on irregular polygon:
        # Use boundary half-plane clipping combined with minimum edge buffer
        min_x, min_y, max_x, max_y = shapely_poly.bounds
        left_s = setbacks.get("left", 0.0)
        right_s = setbacks.get("right", 0.0)
        front_s = setbacks.get("front", 0.0)
        rear_s = setbacks.get("rear", 0.0)

        # First clip against directional bounding half-planes
        clip_poly = Polygon([
            (min_x + left_s, min_y + front_s),
            (max_x - right_s, min_y + front_s),
            (max_x - right_s, max_y - rear_s),
            (min_x + left_s, max_y - rear_s),
        ])
        result = shapely_poly.intersection(clip_poly)
        return extract_largest_polygon(result)

    @staticmethod
    def _check_is_rectangular(coords: list[Tuple[float, float]]) -> bool:
        """Check if polygon vertices form a rectangle."""
        if len(coords) != 4:
            return False
        # Calculate 4 edge vectors and check perpendicularity
        for i in range(4):
            p1 = coords[i]
            p2 = coords[(i + 1) % 4]
            p3 = coords[(i + 2) % 4]
            v1 = (p2[0] - p1[0], p2[1] - p1[1])
            v2 = (p3[0] - p2[0], p3[1] - p2[1])
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            if abs(dot) > 1e-3:
                return False
        return True
