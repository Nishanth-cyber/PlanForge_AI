"""Wall Builder for deterministic wall construction from room boundaries.

Extracts exterior and interior partition walls, deduplicates shared partitions,
computes 2D wall footprint polygons, and associates wall IDs with GeoRoom instances.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Set, Tuple
from shapely.geometry import LineString, Polygon

from app.geometry.geometry_utils import (
    Point2D,
    Segment2D,
    extract_polygon_segments,
    from_shapely_polygon,
    segment_length,
    to_shapely_polygon,
)
from app.models.geometry import GeoRoom, GeoWall
from app.utils.ids import generate_id


def _canonical_segment_key(p1: Point2D, p2: Point2D, tolerance: float = 0.05) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Generate canonical sorted key for segment within tolerance."""
    p1_r = (round(p1[0] / tolerance) * tolerance, round(p1[1] / tolerance) * tolerance)
    p2_r = (round(p2[0] / tolerance) * tolerance, round(p2[1] / tolerance) * tolerance)
    if p1_r > p2_r:
        return (p2_r, p1_r)
    return (p1_r, p2_r)


def _build_wall_polygon(p1: Point2D, p2: Point2D, thickness: float) -> List[Point2D]:
    """Generate 2D rectangular footprint polygon for a wall segment."""
    line = LineString([p1, p2])
    buf = line.buffer(thickness / 2.0, cap_style="flat")
    poly_coords = from_shapely_polygon(buf, round_digits=4)
    if not poly_coords or len(poly_coords) < 3:
        return [p1, p2, p2, p1]
    return poly_coords


class WallBuilder:
    """Constructs exterior and interior partition GeoWalls from constructed rooms."""

    @staticmethod
    def build_walls_for_rooms(
        rooms: List[GeoRoom],
        floor_number: int = 1,
        exterior_thickness: float = 0.20,
        interior_thickness: float = 0.15,
        wall_height: float = 3.0,
        min_wall_length: float = 0.3,
        tolerance: float = 0.08,
    ) -> List[GeoWall]:
        """Construct deterministic GeoWalls for all rooms on a floor.

        Args:
            rooms: List of GeoRooms with constructed built_polygons.
            floor_number: Floor number.
            exterior_thickness: Thickness of exterior walls in meters.
            interior_thickness: Thickness of interior partition walls in meters.
            wall_height: Standard wall height in meters.
            min_wall_length: Minimum length threshold to generate a wall.
            tolerance: Snapping tolerance for shared segments.

        Returns:
            List of constructed GeoWall instances with populated room associations.
        """
        walls: List[GeoWall] = []
        processed_shared_keys: Set[Tuple[Tuple[float, float], Tuple[float, float]]] = set()

        # Step 1: Collect segments per room
        room_segments: List[Tuple[GeoRoom, Segment2D]] = []
        for room in rooms:
            segs = extract_polygon_segments(room.built_polygon)
            for seg in segs:
                if segment_length(seg) >= min_wall_length:
                    room_segments.append((room, seg))

        # Step 2: Classify segments as shared (interior) or unshared (exterior)
        # Check pairwise overlap
        n = len(room_segments)
        matched_pairs: Dict[int, int] = {}

        for i in range(n):
            if i in matched_pairs:
                continue
            room_i, seg_i = room_segments[i]
            line_i = LineString(seg_i)

            for j in range(i + 1, n):
                if j in matched_pairs:
                    continue
                room_j, seg_j = room_segments[j]
                if room_i.id == room_j.id:
                    continue

                line_j = LineString(seg_j)
                inter = line_i.intersection(line_j.buffer(tolerance))
                if not inter.is_empty and hasattr(inter, "length") and inter.length >= min_wall_length:
                    # Shared partition found!
                    matched_pairs[i] = j
                    matched_pairs[j] = i
                    break

        # Step 3: Construct GeoWalls
        visited_indices: Set[int] = set()

        for idx, (room, seg) in enumerate(room_segments):
            if idx in visited_indices:
                continue

            visited_indices.add(idx)
            p1, p2 = seg

            if idx in matched_pairs:
                # Shared interior wall
                other_idx = matched_pairs[idx]
                visited_indices.add(other_idx)
                other_room, other_seg = room_segments[other_idx]

                # Canonicalize key to avoid duplicate generation
                ckey = _canonical_segment_key(p1, p2, tolerance=tolerance)
                if ckey in processed_shared_keys:
                    continue
                processed_shared_keys.add(ckey)

                wall_poly = _build_wall_polygon(p1, p2, interior_thickness)
                wall = GeoWall(
                    id=generate_id("geowall"),
                    start=(round(p1[0], 4), round(p1[1], 4)),
                    end=(round(p2[0], 4), round(p2[1], 4)),
                    thickness=interior_thickness,
                    height=wall_height,
                    type="interior",
                    floor_number=floor_number,
                    polygon=wall_poly,
                    room_ids=[room.id, other_room.id],
                )
                walls.append(wall)

                # Associate wall ID with both rooms
                if wall.id not in room.walls:
                    room.walls.append(wall.id)
                if wall.id not in other_room.walls:
                    other_room.walls.append(wall.id)

            else:
                # Exterior wall
                wall_poly = _build_wall_polygon(p1, p2, exterior_thickness)
                wall = GeoWall(
                    id=generate_id("geowall"),
                    start=(round(p1[0], 4), round(p1[1], 4)),
                    end=(round(p2[0], 4), round(p2[1], 4)),
                    thickness=exterior_thickness,
                    height=wall_height,
                    type="exterior",
                    floor_number=floor_number,
                    polygon=wall_poly,
                    room_ids=[room.id],
                )
                walls.append(wall)

                if wall.id not in room.walls:
                    room.walls.append(wall.id)

        return walls
