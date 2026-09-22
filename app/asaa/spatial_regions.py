"""Spatial region geometric definitions and utilities for ASAA."""

from __future__ import annotations
import math
from typing import Optional, Tuple
from shapely.geometry import Polygon, LineString, MultiLineString


def create_rectangular_region(
    x: float,
    y: float,
    width: float,
    height: float,
    room_type: str = "",
) -> list[Tuple[float, float]]:
    """Create a rectangular spatial region polygon vertices."""
    return [
        (round(x, 4), round(y, 4)),
        (round(x + width, 4), round(y, 4)),
        (round(x + width, 4), round(y + height, 4)),
        (round(x, 4), round(y + height, 4)),
    ]


def calculate_region_area(polygon: list[Tuple[float, float]]) -> float:
    """Calculate area of a polygon using shoelace formula."""
    if len(polygon) < 3:
        return 0.0

    area = 0.0
    n = len(polygon)
    for i in range(n):
        j = (i + 1) % n
        area += polygon[i][0] * polygon[j][1]
        area -= polygon[j][0] * polygon[i][1]

    return abs(area) / 2.0


def calculate_centroid(polygon: list[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Calculate centroid of a polygon."""
    if len(polygon) < 3:
        return None

    area = calculate_region_area(polygon)
    if area == 0:
        return None

    cx = 0.0
    cy = 0.0
    n = len(polygon)
    for i in range(n):
        j = (i + 1) % n
        cross = polygon[i][0] * polygon[j][1] - polygon[j][0] * polygon[i][1]
        cx += (polygon[i][0] + polygon[j][0]) * cross
        cy += (polygon[i][1] + polygon[j][1]) * cross

    return (round(cx / (6 * area), 4), round(cy / (6 * area), 4))


def calculate_approximate_dimensions(polygon: list[Tuple[float, float]]) -> Tuple[float, float]:
    """Calculate approximate (width, length) in meters from bounding box."""
    if len(polygon) < 3:
        return (0.0, 0.0)

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    # Convention: width is the smaller dimension, length is larger
    return (round(min(w, h), 2), round(max(w, h), 2))


def calculate_aspect_ratio(polygon: list[Tuple[float, float]]) -> float:
    """Calculate aspect ratio (max dimension / min dimension) of bounding box."""
    w, l = calculate_approximate_dimensions(polygon)
    if w <= 0:
        return 1.0
    return round(l / w, 2)


def calculate_shared_boundary_length(
    poly_a: list[Tuple[float, float]], poly_b: list[Tuple[float, float]]
) -> float:
    """Calculate shared boundary contact length between two polygons in meters."""
    if len(poly_a) < 3 or len(poly_b) < 3:
        return 0.0

    sa = Polygon(poly_a)
    sb = Polygon(poly_b)
    if not sa.is_valid or not sb.is_valid:
        return 0.0

    # The shared boundary is the intersection of their boundary lines
    line_intersection = sa.boundary.intersection(sb.boundary)
    if line_intersection.is_empty:
        return 0.0

    if isinstance(line_intersection, (LineString, MultiLineString)):
        return round(float(line_intersection.length), 3)

    return 0.0


def are_regions_adjacent(
    poly_a: list[Tuple[float, float]],
    poly_b: list[Tuple[float, float]],
    min_contact_m: float = 0.2,
) -> bool:
    """Check if two region polygons share physical boundary contact."""
    return calculate_shared_boundary_length(poly_a, poly_b) >= min_contact_m


def calculate_isoperimetric_quotient(polygon: list[Tuple[float, float]]) -> float:
    """Calculate compactness quotient: 4 * pi * Area / Perimeter^2 (1.0 = circle)."""
    if len(polygon) < 3:
        return 0.0

    poly = Polygon(polygon)
    if not poly.is_valid or poly.length <= 0:
        return 0.0

    return round(4 * math.pi * poly.area / (poly.length ** 2), 3)


def is_point_in_polygon(
    x: float,
    y: float,
    polygon: list[Tuple[float, float]],
) -> bool:
    """Check if a point is inside a polygon."""
    if len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)
    j = n - 1

    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi) + xi
        ):
            inside = not inside

        j = i

    return inside
