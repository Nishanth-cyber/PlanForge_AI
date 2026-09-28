"""Door Builder for constructing physical GeoDoor instances from DoorIntents.

Realizes architectural door intents onto physical GeoWalls, calculates exact door opening
positions, and generates 90-degree swing arc polygons.
"""

from __future__ import annotations
import math
from typing import List, Optional
from shapely.geometry import LineString

from app.geometry.exceptions import DoorPlacementError
from app.geometry.geometry_utils import (
    Point2D,
    compute_swing_arc,
    get_wall_orientation,
    point_along_segment,
    segment_length,
)
from app.models.doors import DoorIntent
from app.models.geometry import GeoDoor, GeoRoom, GeoWall
from app.utils.ids import generate_id


class DoorBuilder:
    """Constructs physical GeoDoor instances from DoorIntent proposals."""

    @staticmethod
    def build_door(
        door_intent: DoorIntent,
        walls: List[GeoWall],
        rooms: List[GeoRoom],
        floor_number: int = 1,
        source_room_override: Optional[GeoRoom] = None,
    ) -> GeoDoor:
        """Construct a physical GeoDoor on a matching GeoWall.

        Args:
            door_intent: Architectural door proposal (HOW).
            walls: List of constructed GeoWalls for the floor.
            rooms: List of constructed GeoRooms for the floor.
            floor_number: Floor number.
            source_room_override: Optional pre-resolved source GeoRoom.

        Returns:
            GeoDoor with valid wall placement and computed swing arc.

        Raises:
            DoorPlacementError: If no suitable wall exists or wall is too narrow.
        """
        # Find source room
        source_room = source_room_override
        if not source_room:
            for r in rooms:
                if r.id == door_intent.connects_from or r.room_type == door_intent.connects_from or r.architectural_room_id == door_intent.connects_from:
                    source_room = r
                    break

        target_room = None
        for r in rooms:
            if r.id == door_intent.connects_to or r.room_type == door_intent.connects_to or r.architectural_room_id == door_intent.connects_to:
                target_room = r
                break

        door_type = door_intent.door_type or "interior"
        req_width = door_intent.recommended_width or 0.9
        req_height = door_intent.recommended_height or 2.1

        target_wall: Optional[GeoWall] = None

        if door_type in {"entrance", "exterior", "balcony"} or door_intent.connects_to in {"exterior", "balcony"}:
            # Search for exterior wall belonging to source room
            candidate_walls: List[GeoWall] = []
            if source_room:
                candidate_walls = [w for w in walls if w.id in source_room.walls and w.type == "exterior"]
            if not candidate_walls:
                candidate_walls = [w for w in walls if w.type == "exterior"]

            # Prioritize requested orientation
            if door_intent.wall_orientation and candidate_walls:
                orient_norm = door_intent.wall_orientation.lower().strip()
                matching = [
                    w for w in candidate_walls
                    if get_wall_orientation((w.start, w.end)) == orient_norm
                ]
                for w in sorted(matching, key=lambda wall: segment_length((wall.start, wall.end)), reverse=True):
                    if segment_length((w.start, w.end)) >= req_width - 0.05:
                        target_wall = w
                        break

            # Fallback to widest available exterior wall
            if not target_wall:
                for w in sorted(candidate_walls, key=lambda wall: segment_length((wall.start, wall.end)), reverse=True):
                    if segment_length((w.start, w.end)) >= req_width - 0.05:
                        target_wall = w
                        break

        elif target_room is not None and source_room is not None:
            # Interior door between two specific rooms: must share a partition wall
            shared_walls = [w for w in walls if source_room.id in w.room_ids and target_room.id in w.room_ids]
            for w in shared_walls:
                if segment_length((w.start, w.end)) >= req_width - 0.05:
                    target_wall = w
                    break

            if not target_wall and not shared_walls:
                # If no shared wall exists between these rooms, direct door is impossible
                raise DoorPlacementError(
                    f"Rooms '{source_room.room_type}' and '{target_room.room_type}' are not adjacent; "
                    f"cannot place direct door intent {door_intent.id}"
                )

        else:
            # Connecting to circulation, corridor, or general partition
            candidate_walls = []
            if source_room:
                # Prefer walls shared with a corridor room if one exists
                corridor_rooms = [r for r in rooms if r.is_corridor or r.room_type in {"circulation", "corridor"}]
                if corridor_rooms:
                    for corr in corridor_rooms:
                        shared = [w for w in walls if source_room.id in w.room_ids and corr.id in w.room_ids]
                        candidate_walls.extend(shared)
                if not candidate_walls:
                    candidate_walls = [w for w in walls if w.id in source_room.walls and w.type == "interior"]
            if not candidate_walls and source_room:
                candidate_walls = [w for w in walls if w.id in source_room.walls]

            # Prioritize requested orientation if specified
            if door_intent.wall_orientation and candidate_walls:
                orient_norm = door_intent.wall_orientation.lower().strip()
                matching = [
                    w for w in candidate_walls
                    if get_wall_orientation((w.start, w.end)) == orient_norm
                ]
                for w in sorted(matching, key=lambda wall: segment_length((wall.start, wall.end)), reverse=True):
                    if segment_length((w.start, w.end)) >= req_width - 0.05:
                        target_wall = w
                        break

            # Fallback to any suitable interior/partition wall for that room
            if not target_wall:
                for w in sorted(candidate_walls, key=lambda wall: segment_length((wall.start, wall.end)), reverse=True):
                    if segment_length((w.start, w.end)) >= req_width - 0.05:
                        target_wall = w
                        break

        if not target_wall:
            raise DoorPlacementError(
                f"Cannot place door intent {door_intent.id} (connects '{door_intent.connects_from}' to "
                f"'{door_intent.connects_to}'): no wall with sufficient width (>= {req_width}m) found"
            )

        # Place door at midpoint of wall
        w_start = target_wall.start
        w_end = target_wall.end
        w_len = segment_length((w_start, w_end))
        pos = point_along_segment((w_start, w_end), 0.5)

        # Compute hinge point (at midpoint minus half width)
        half_frac = (req_width / 2.0) / w_len
        hinge = point_along_segment((w_start, w_end), max(0.05, 0.5 - half_frac))

        # Compute swing arc: orient swing inward towards room interior
        swing_inside = True
        ref_room = source_room or target_room
        if ref_room and ref_room.usable_polygon:
            from shapely.geometry import Polygon
            p = Polygon(ref_room.usable_polygon)
            rcx, rcy = p.centroid.x, p.centroid.y
            to_rcx = rcx - pos[0]
            to_rcy = rcy - pos[1]
            wx = w_end[0] - w_start[0]
            wy = w_end[1] - w_start[1]
            # Inward normal (+pi/2) has vector (-wy, wx)
            dot_in = -wy * to_rcx + wx * to_rcy
            swing_inside = (dot_in >= 0)

        swing_arc = compute_swing_arc(
            hinge=hinge,
            wall_start=w_start,
            wall_end=w_end,
            width=req_width,
            swing_inside=swing_inside,
        )

        geo_door = GeoDoor(
            id=generate_id("geodoor"),
            wall_id=target_wall.id,
            position=(round(pos[0], 4), round(pos[1], 4)),
            width=req_width,
            height=req_height,
            type=door_type,
            connects_from=door_intent.connects_from,
            connects_to=door_intent.connects_to,
            swing_arc=swing_arc,
            floor_number=floor_number,
            intent_id=door_intent.id,
        )

        # Update room associations
        if source_room and geo_door.id not in source_room.doors:
            source_room.doors.append(geo_door.id)
        if target_room and geo_door.id not in target_room.doors:
            target_room.doors.append(geo_door.id)

        return geo_door
