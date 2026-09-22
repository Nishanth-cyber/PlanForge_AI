"""Deterministic geometric utilities for PlanForge AI.

Wraps Shapely for polygon validation, containment, intersection, segment extraction,
wall normal computation, and door swing arc generation.
"""

from __future__ import annotations
import math
from typing import Any, List, Optional, Tuple
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
from shapely.validation import make_valid

from app.geometry.exceptions import InvalidRoomGeometryError

Point2D = Tuple[float, float]
Segment2D = Tuple[Point2D, Point2D]


def extract_largest_polygon(geom: Any) -> Polygon:
    """Safely extract the largest 2D Polygon from any Shapely geometry result.

    Handles Polygon, MultiPolygon, GeometryCollection, and nested geometries.
    """
    if geom is None or geom.is_empty:
        return Polygon()
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        polys = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        return max(polys, key=lambda g: g.area) if polys else Polygon()
    if isinstance(geom, GeometryCollection):
        polys = []
        for g in geom.geoms:
            if isinstance(g, Polygon) and not g.is_empty:
                polys.append(g)
            elif isinstance(g, MultiPolygon):
                polys.extend([p for p in g.geoms if isinstance(p, Polygon) and not p.is_empty])
            elif isinstance(g, GeometryCollection):
                sub_poly = extract_largest_polygon(g)
                if not sub_poly.is_empty:
                    polys.append(sub_poly)
        return max(polys, key=lambda g: g.area) if polys else Polygon()
    return Polygon()


def to_shapely_polygon(coords: List[Point2D]) -> Polygon:
    """Convert coordinate list to Shapely Polygon, ensuring ring closure."""
    if not coords or len(coords) < 3:
        raise InvalidRoomGeometryError(f"Polygon requires at least 3 coordinates, got {len(coords)}")
    if coords[0] != coords[-1]:
        coords = list(coords) + [coords[0]]
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = make_valid(poly)
        poly = extract_largest_polygon(poly)
    return poly


def from_shapely_polygon(poly: Any, round_digits: int = 4) -> List[Point2D]:
    """Convert Shapely Polygon (or GeometryCollection/MultiPolygon) to list of rounded (x, y) coordinates."""
    if poly is None or poly.is_empty:
        return []
    if not isinstance(poly, Polygon):
        poly = extract_largest_polygon(poly)
    if poly.is_empty or not hasattr(poly, "exterior") or poly.exterior is None:
        return []
    coords = list(poly.exterior.coords)
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(round(x, round_digits), round(y, round_digits)) for x, y in coords]


def validate_polygon_coords(coords: List[Point2D]) -> None:
    """Validate polygon coordinates. Raises InvalidRoomGeometryError on invalid geometry."""
    if not coords or len(coords) < 3:
        raise InvalidRoomGeometryError(f"Polygon has fewer than 3 coordinates: {len(coords)}")
    poly = to_shapely_polygon(coords)
    if poly.is_empty:
        raise InvalidRoomGeometryError("Constructed polygon is empty")
    if poly.area <= 1e-6:
        raise InvalidRoomGeometryError(f"Polygon has non-positive or negligible area: {poly.area}")


def polygon_area(coords: List[Point2D]) -> float:
    """Compute 2D polygon area."""
    if len(coords) < 3:
        return 0.0
    poly = to_shapely_polygon(coords)
    return float(poly.area)


def is_contained_in(child_coords: List[Point2D], parent_coords: List[Point2D], tolerance: float = 0.05) -> bool:
    """Check if child polygon is contained within parent polygon, allowing minor boundary tolerance."""
    if not child_coords or not parent_coords:
        return False
    child_poly = to_shapely_polygon(child_coords)
    parent_poly = to_shapely_polygon(parent_coords)
    if tolerance > 0:
        parent_poly = parent_poly.buffer(tolerance)
    return bool(parent_poly.contains(child_poly) or parent_poly.covers(child_poly))


def extract_polygon_segments(coords: List[Point2D]) -> List[Segment2D]:
    """Extract individual directed line segments from polygon vertices."""
    clean = list(coords)
    if len(clean) > 1 and clean[0] == clean[-1]:
        clean = clean[:-1]
    n = len(clean)
    if n < 2:
        return []
    segments: List[Segment2D] = []
    for i in range(n):
        p1 = clean[i]
        p2 = clean[(i + 1) % n]
        segments.append((p1, p2))
    return segments


def segment_length(seg: Segment2D) -> float:
    """Calculate Euclidean length of segment."""
    p1, p2 = seg
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def segment_midpoint(seg: Segment2D) -> Point2D:
    """Calculate midpoint of segment."""
    p1, p2 = seg
    return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)


def point_along_segment(seg: Segment2D, fraction: float) -> Point2D:
    """Get point along segment at normalized fraction (0.0 to 1.0)."""
    p1, p2 = seg
    return (
        p1[0] + fraction * (p2[0] - p1[0]),
        p1[1] + fraction * (p2[1] - p1[1]),
    )


def find_shared_wall_segment(
    poly_a_coords: List[Point2D],
    poly_b_coords: List[Point2D],
    min_length: float = 0.4,
    tolerance: float = 0.05,
) -> Optional[Segment2D]:
    """Find shared linear wall segment between two adjacent room polygons.

    Returns longest shared segment if length >= min_length, else None.
    """
    poly_a = to_shapely_polygon(poly_a_coords)
    poly_b = to_shapely_polygon(poly_b_coords)

    # Use boundary intersection with small buffer
    line_a = poly_a.boundary
    line_b = poly_b.boundary
    shared = line_a.intersection(line_b.buffer(tolerance))

    candidates: List[Segment2D] = []
    if isinstance(shared, LineString) and not shared.is_empty:
        c = list(shared.coords)
        if len(c) >= 2:
            candidates.append(((c[0][0], c[0][1]), (c[-1][0], c[-1][1])))
    elif isinstance(shared, MultiLineString):
        for geom in shared.geoms:
            c = list(geom.coords)
            if len(c) >= 2:
                candidates.append(((c[0][0], c[0][1]), (c[-1][0], c[-1][1])))
    elif isinstance(shared, (Polygon, MultiPolygon)):
        # If intersection expanded to a 2D strip, extract centerline or boundary segments
        b = shared.boundary
        if isinstance(b, LineString):
            c = list(b.coords)
            if len(c) >= 2:
                candidates.append(((c[0][0], c[0][1]), (c[-1][0], c[-1][1])))
        elif isinstance(b, MultiLineString):
            for g in b.geoms:
                c = list(g.coords)
                if len(c) >= 2:
                    candidates.append(((c[0][0], c[0][1]), (c[-1][0], c[-1][1])))

    # Also check segment-by-segment colinearity as a robust geometric fallback
    if not candidates:
        segs_a = extract_polygon_segments(poly_a_coords)
        segs_b = extract_polygon_segments(poly_b_coords)
        for sa in segs_a:
            la = LineString(sa)
            for sb in segs_b:
                lb = LineString(sb)
                inter = la.intersection(lb.buffer(tolerance))
                if not inter.is_empty and hasattr(inter, "length") and inter.length >= min_length:
                    # Overlap interval on segment sa
                    coords = list(inter.envelope.boundary.coords) if hasattr(inter, "envelope") else []
                    if len(coords) >= 2:
                        candidates.append((sa[0], sa[1]))

    if not candidates:
        return None

    # Pick the longest candidate
    best = max(candidates, key=segment_length)
    if segment_length(best) >= min_length:
        return (
            (round(best[0][0], 4), round(best[0][1], 4)),
            (round(best[1][0], 4), round(best[1][1], 4)),
        )
    return None


def get_wall_orientation(seg: Segment2D, room_centroid: Optional[Point2D] = None) -> str:
    """Determine wall compass orientation ('north', 'south', 'east', 'west').

    Uses outward normal pointing away from room_centroid if provided,
    otherwise uses segment slope/direction.
    """
    (x1, y1), (x2, y2) = seg
    dx = x2 - x1
    dy = y2 - y1

    # Candidate normals: (-dy, dx) and (dy, -dx)
    n1 = (-dy, dx)
    n2 = (dy, -dx)

    if room_centroid is not None:
        cx, cy = room_centroid
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        # Outward normal dot with vector from centroid to midpoint must be positive
        to_mid_x = mx - cx
        to_mid_y = my - cy
        dot1 = n1[0] * to_mid_x + n1[1] * to_mid_y
        out_normal = n1 if dot1 >= 0 else n2
    else:
        # Default CCW normal
        out_normal = n1

    nx, ny = out_normal
    norm = math.hypot(nx, ny)
    if norm > 1e-6:
        nx /= norm
        ny /= norm

    # Classify into primary 4 compass directions
    if abs(nx) > abs(ny):
        return "east" if nx > 0 else "west"
    else:
        return "north" if ny > 0 else "south"


def offset_polygon(coords: List[Point2D], distance: float) -> List[Point2D]:
    """Offset polygon inwards (distance < 0) or outwards (distance > 0).

    Uses mitre or square joins to preserve architectural right angles.
    """
    poly = to_shapely_polygon(coords)
    # distance is offset: negative is inward buffer
    offset = poly.buffer(distance, join_style="mitre", mitre_limit=2.0)
    if offset.is_empty:
        # Fallback: smaller offset or original if buffer collapsed
        offset = poly.buffer(distance * 0.5, join_style="mitre", mitre_limit=2.0)
        if offset.is_empty:
            return coords

    if isinstance(offset, MultiPolygon):
        offset = max(offset.geoms, key=lambda g: g.area)

    res = from_shapely_polygon(offset)
    return res if len(res) >= 3 else coords


def compute_swing_arc(
    hinge: Point2D,
    wall_start: Point2D,
    wall_end: Point2D,
    width: float,
    swing_inside: bool = True,
    num_samples: int = 8,
) -> List[Point2D]:
    """Compute 2D swing arc polygon vertices for a door leaf.

    Constructs a 90-degree sector polygon originating from hinge.
    """
    hx, hy = hinge
    wx = wall_end[0] - wall_start[0]
    wy = wall_end[1] - wall_start[1]
    w_len = math.hypot(wx, wy)
    if w_len < 1e-6:
        # Default horizontal
        wall_angle = 0.0
    else:
        wall_angle = math.atan2(wy, wx)

    # Inward normal (+90 deg or -90 deg)
    swing_dir = 1.0 if swing_inside else -1.0
    start_angle = wall_angle
    sweep_angle = swing_dir * (math.pi / 2.0)

    arc_vertices: List[Point2D] = [(round(hx, 4), round(hy, 4))]
    for i in range(num_samples + 1):
        frac = i / float(num_samples)
        a = start_angle + frac * sweep_angle
        ax = hx + width * math.cos(a)
        ay = hy + width * math.sin(a)
        arc_vertices.append((round(ax, 4), round(ay, 4)))

    return arc_vertices
