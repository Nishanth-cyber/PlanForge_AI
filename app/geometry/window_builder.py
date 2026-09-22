"""Window Builder for constructing physical GeoWindow instances from WindowIntents.

Realizes architectural window intents onto exterior GeoWalls matching requested
compass orientation and sill heights.
"""

from __future__ import annotations
from typing import List, Optional

from app.geometry.exceptions import WindowPlacementError
from app.geometry.geometry_utils import (
    get_wall_orientation,
    point_along_segment,
    segment_length,
)
from app.models.geometry import GeoRoom, GeoWall, GeoWindow
from app.models.windows import WindowIntent
from app.utils.ids import generate_id


class WindowBuilder:
    """Constructs physical GeoWindow instances from WindowIntent proposals."""

    @staticmethod
    def build_window(
        window_intent: WindowIntent,
        walls: List[GeoWall],
        rooms: List[GeoRoom],
        floor_number: int = 1,
        target_room_override: Optional[GeoRoom] = None,
    ) -> GeoWindow:
        """Construct a physical GeoWindow on a matching exterior GeoWall.

        Args:
            window_intent: Architectural window proposal (HOW).
            walls: List of constructed GeoWalls for the floor.
            rooms: List of constructed GeoRooms for the floor.
            floor_number: Floor number.
            target_room_override: Optional pre-resolved target GeoRoom.

        Returns:
            GeoWindow placed on a suitable exterior wall.

        Raises:
            WindowPlacementError: If no exterior wall matches orientation or width.
        """
        # Find target room
        target_room = target_room_override
        if not target_room:
            for r in rooms:
                if (
                    r.id == window_intent.room_id
                    or r.room_type == window_intent.room_id
                    or r.architectural_room_id == window_intent.room_id
                ):
                    target_room = r
                    break

        req_width = window_intent.recommended_width or 1.2
        req_height = window_intent.recommended_height or 1.2
        sill_height = window_intent.sill_height or 0.9
        w_type = window_intent.window_type or "standard"

        # Candidate walls: must be exterior
        candidate_walls: List[GeoWall] = []
        if target_room:
            candidate_walls = [w for w in walls if w.id in target_room.walls and w.type == "exterior"]
        else:
            candidate_walls = [w for w in walls if w.type == "exterior"]

        if not candidate_walls:
            raise WindowPlacementError(
                f"No exterior walls available for room '{window_intent.room_id}' (intent {window_intent.id})"
            )

        # Filter by requested orientation if provided
        target_wall: Optional[GeoWall] = None
        if window_intent.wall_orientation:
            orient_norm = window_intent.wall_orientation.lower().strip()
            # Try with room centroid if room found
            room_cent = None
            if target_room and target_room.usable_polygon:
                from shapely.geometry import Polygon
                p = Polygon(target_room.usable_polygon)
                room_cent = (p.centroid.x, p.centroid.y)

            matching_walls = [
                w for w in candidate_walls
                if get_wall_orientation((w.start, w.end), room_cent) == orient_norm
            ]
            for w in sorted(matching_walls, key=lambda wall: segment_length((wall.start, wall.end)), reverse=True):
                if segment_length((w.start, w.end)) >= req_width - 0.05:
                    target_wall = w
                    break

        # Fallback to widest available exterior wall for that room
        if not target_wall:
            for w in sorted(candidate_walls, key=lambda wall: segment_length((wall.start, wall.end)), reverse=True):
                if segment_length((w.start, w.end)) >= req_width - 0.05:
                    target_wall = w
                    break

        if not target_wall:
            raise WindowPlacementError(
                f"Exterior walls for room '{window_intent.room_id}' are too narrow for window width {req_width}m"
            )

        # Place centered along wall
        w_start = target_wall.start
        w_end = target_wall.end
        pos = point_along_segment((w_start, w_end), 0.5)

        geo_window = GeoWindow(
            id=generate_id("geowindow"),
            wall_id=target_wall.id,
            position=(round(pos[0], 4), round(pos[1], 4)),
            width=req_width,
            height=req_height,
            sill_height=sill_height,
            type=w_type,
            floor_number=floor_number,
            intent_id=window_intent.id,
        )

        if target_room and geo_window.id not in target_room.windows:
            target_room.windows.append(geo_window.id)

        return geo_window
