"""Polygon Builder for deterministic semantic room shapes.

Constructs rectangular, square, and L-shaped room boundaries strictly within
their assigned ASAA allocated regions.
"""

from __future__ import annotations
import math
from typing import List, Optional, Tuple
from shapely.geometry import Polygon

from app.geometry.exceptions import (
    ImpossibleDimensionsError,
    InvalidRoomGeometryError,
    InvalidShapeParametersError,
    RoomOutOfBoundsError,
)
from app.geometry.geometry_utils import (
    Point2D,
    from_shapely_polygon,
    is_contained_in,
    to_shapely_polygon,
    validate_polygon_coords,
)


class PolygonBuilder:
    """Deterministic builder for room boundary polygons."""

    @staticmethod
    def construct_rectangle(
        region_coords: List[Point2D],
        width: float,
        length: float,
        anchor: str = "center",
        tolerance: float = 0.05,
    ) -> List[Point2D]:
        """Construct a rectangular polygon within an allocated region.

        Args:
            region_coords: Assigned ASAA allocated region polygon coordinates.
            width: Room width (along X axis).
            length: Room length (along Y axis).
            anchor: Positioning alignment ("center", "south_west", "north_west").
            tolerance: Geometric containment tolerance.

        Returns:
            List of 4 (x, y) coordinates representing the rectangle.

        Raises:
            ImpossibleDimensionsError: If width or length are non-positive or larger than region envelope.
            RoomOutOfBoundsError: If constructed rectangle exceeds allocated region.
        """
        if width <= 0 or length <= 0:
            raise ImpossibleDimensionsError(f"Dimensions must be positive, got width={width}, length={length}")

        region_poly = to_shapely_polygon(region_coords)
        min_x, min_y, max_x, max_y = region_poly.bounds
        reg_w = max_x - min_x
        reg_l = max_y - min_y

        # If requested (width, length) exceeds envelope but rotated (length, width) fits, align with region orientation
        if (width > reg_w + tolerance or length > reg_l + tolerance) and (
            length <= reg_w + tolerance and width <= reg_l + tolerance
        ):
            width, length = length, width

        if width > reg_w + tolerance or length > reg_l + tolerance:
            raise ImpossibleDimensionsError(
                f"Requested dimensions ({width:.2f}m x {length:.2f}m) exceed region envelope "
                f"({reg_w:.2f}m x {reg_l:.2f}m)"
            )

        if anchor == "center":
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            x1 = cx - width / 2.0
            y1 = cy - length / 2.0
        elif anchor == "south_west":
            x1 = min_x
            y1 = min_y
        elif anchor == "north_west":
            x1 = min_x
            y1 = max_y - length
        else:
            x1 = (min_x + max_x) / 2.0 - width / 2.0
            y1 = (min_y + max_y) / 2.0 - length / 2.0

        x2 = x1 + width
        y2 = y1 + length

        rect_coords: List[Point2D] = [
            (round(x1, 4), round(y1, 4)),
            (round(x2, 4), round(y1, 4)),
            (round(x2, 4), round(y2, 4)),
            (round(x1, 4), round(y2, 4)),
        ]

        # Verify containment
        if not is_contained_in(rect_coords, region_coords, tolerance=tolerance):
            # If centered was slightly outside irregular boundary, try anchoring at centroid
            cent = region_poly.centroid
            x1_c = cent.x - width / 2.0
            y1_c = cent.y - length / 2.0
            rect_coords_c: List[Point2D] = [
                (round(x1_c, 4), round(y1_c, 4)),
                (round(x1_c + width, 4), round(y1_c, 4)),
                (round(x1_c + width, 4), round(y1_c + length, 4)),
                (round(x1_c, 4), round(y1_c + length, 4)),
            ]
            if is_contained_in(rect_coords_c, region_coords, tolerance=tolerance):
                rect_coords = rect_coords_c
            else:
                raise RoomOutOfBoundsError(
                    f"Constructed rectangle ({width:.2f}x{length:.2f}) extends outside allocated region"
                )

        validate_polygon_coords(rect_coords)
        return rect_coords

    @staticmethod
    def construct_square(
        region_coords: List[Point2D],
        area: float,
        anchor: str = "center",
        tolerance: float = 0.05,
    ) -> List[Point2D]:
        """Construct a square polygon of specified area within region."""
        if area <= 0:
            raise ImpossibleDimensionsError(f"Square area must be positive, got {area}")
        side = math.sqrt(area)
        region_poly = to_shapely_polygon(region_coords)
        min_x, min_y, max_x, max_y = region_poly.bounds
        reg_w = max_x - min_x
        reg_l = max_y - min_y
        max_fit = min(reg_w, reg_l)
        if side > max_fit:
            side = max_fit
        return PolygonBuilder.construct_rectangle(
            region_coords=region_coords,
            width=side,
            length=side,
            anchor=anchor,
            tolerance=tolerance,
        )

    @staticmethod
    def construct_l_shaped(
        region_coords: List[Point2D],
        w1: Optional[float] = None,
        l1: Optional[float] = None,
        w2: Optional[float] = None,
        l2: Optional[float] = None,
        cutout_quadrant: str = "north_east",
        tolerance: float = 0.05,
    ) -> List[Point2D]:
        """Construct an orthogonal 6-vertex L-shaped room polygon.

        An L-shape is formed by a bounding box (W x L) with one quadrant removed.
        If parameters are not provided, defaults to removing a 40% cutout from the region envelope.
        """
        region_poly = to_shapely_polygon(region_coords)
        min_x, min_y, max_x, max_y = region_poly.bounds
        W = max_x - min_x
        L = max_y - min_y

        if W <= 0.5 or L <= 0.5:
            raise ImpossibleDimensionsError(f"Region is too small for L-shape: {W}x{L}")

        if (w2 is not None and w2 >= W) or (l2 is not None and l2 >= L):
            raise InvalidShapeParametersError(f"L-shape cutouts ({w2}, {l2}) must be smaller than envelope ({W}, {L})")

        cut_w = w2 if w2 is not None else W * 0.4
        cut_l = l2 if l2 is not None else L * 0.4

        if cut_w >= W or cut_l >= L:
            raise InvalidShapeParametersError(f"L-shape cutouts ({cut_w}, {cut_l}) must be smaller than envelope ({W}, {L})")

        # 6-vertex L-shape orthogonal polygon
        if cutout_quadrant == "north_east":
            # (min_x, min_y) -> (max_x, min_y) -> (max_x, max_y - cut_l) ->
            # (max_x - cut_w, max_y - cut_l) -> (max_x - cut_w, max_y) -> (min_x, max_y)
            coords: List[Point2D] = [
                (round(min_x, 4), round(min_y, 4)),
                (round(max_x, 4), round(min_y, 4)),
                (round(max_x, 4), round(max_y - cut_l, 4)),
                (round(max_x - cut_w, 4), round(max_y - cut_l, 4)),
                (round(max_x - cut_w, 4), round(max_y, 4)),
                (round(min_x, 4), round(max_y, 4)),
            ]
        elif cutout_quadrant == "north_west":
            coords = [
                (round(min_x, 4), round(min_y, 4)),
                (round(max_x, 4), round(min_y, 4)),
                (round(max_x, 4), round(max_y, 4)),
                (round(min_x + cut_w, 4), round(max_y, 4)),
                (round(min_x + cut_w, 4), round(max_y - cut_l, 4)),
                (round(min_x, 4), round(max_y - cut_l, 4)),
            ]
        elif cutout_quadrant == "south_east":
            coords = [
                (round(min_x, 4), round(min_y, 4)),
                (round(max_x - cut_w, 4), round(min_y, 4)),
                (round(max_x - cut_w, 4), round(min_y + cut_l, 4)),
                (round(max_x, 4), round(min_y + cut_l, 4)),
                (round(max_x, 4), round(max_y, 4)),
                (round(min_x, 4), round(max_y, 4)),
            ]
        else:  # south_west
            coords = [
                (round(min_x + cut_w, 4), round(min_y, 4)),
                (round(max_x, 4), round(min_y, 4)),
                (round(max_x, 4), round(max_y, 4)),
                (round(min_x, 4), round(max_y, 4)),
                (round(min_x, 4), round(min_y + cut_l, 4)),
                (round(min_x + cut_w, 4), round(min_y + cut_l, 4)),
            ]

        if not is_contained_in(coords, region_coords, tolerance=tolerance):
            raise RoomOutOfBoundsError("L-shaped polygon extends outside allocated region")

        validate_polygon_coords(coords)
        return coords

    @classmethod
    def construct_from_intent(
        cls,
        shape: str,
        region_coords: List[Point2D],
        intended_dimensions: Optional[Tuple[float, float]] = None,
        intended_area: float = 0.0,
        proposed_boundary: Optional[List[Point2D]] = None,
    ) -> List[Point2D]:
        """Construct physical room polygon based on architectural shape intent and ASAA allocated region."""
        # If proposed_boundary is provided, strictly verify containment
        if proposed_boundary and len(proposed_boundary) >= 3:
            if not is_contained_in(proposed_boundary, region_coords, tolerance=0.05):
                raise RoomOutOfBoundsError(
                    "Architectural proposed room boundary extends outside allocated region"
                )
            validate_polygon_coords(proposed_boundary)
            return proposed_boundary

        shape_norm = (shape or "rectangular").lower().strip()

        if shape_norm in {"rectangular", "rectangle"}:
            if intended_dimensions and intended_dimensions[0] > 0 and intended_dimensions[1] > 0:
                w, l = intended_dimensions
                # If dimensions match region bounds (in either orientation), return region directly
                reg_p = to_shapely_polygon(region_coords)
                min_x, min_y, max_x, max_y = reg_p.bounds
                reg_w = max_x - min_x
                reg_l = max_y - min_y
                if (abs(reg_w - w) < 0.15 and abs(reg_l - l) < 0.15) or (abs(reg_w - l) < 0.15 and abs(reg_l - w) < 0.15):
                    return region_coords
                return cls.construct_rectangle(region_coords, width=w, length=l)
            else:
                # Fill region directly
                return region_coords

        elif shape_norm == "square":
            area = intended_area
            if area <= 0:
                p = to_shapely_polygon(region_coords)
                area = float(p.area)
            return cls.construct_square(region_coords, area=area)

        elif shape_norm in {"l_shaped", "l-shaped"}:
            if len(region_coords) == 6:
                return region_coords
            return cls.construct_l_shaped(region_coords)

        # Default fallback: strictly preserve assigned allocated region boundary
        validate_polygon_coords(region_coords)
        return region_coords
