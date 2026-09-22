"""Connectivity Validator for independent BFS door-graph reachability analysis.

Builds a physical connectivity graph directly from constructed GeoDoors and GeoRooms,
verifying that no required rooms are isolated and that the primary entrance reaches the interior.
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Set

from app.models.geometry import Geometry, GeoDoor, GeoRoom
from app.models.validation import ValidationIssue


class ConnectivityValidator:
    """Independently verifies spatial reachability using graph traversal over physical doors."""

    def validate(self, geometry: Geometry) -> List[ValidationIssue]:
        """Validate door-based reachability and room isolation for a single floor.

        Args:
            geometry: Floor Geometry containing rooms, walls, doors.

        Returns:
            List of ValidationIssue instances for any disconnected or isolated spaces.
        """
        issues: List[ValidationIssue] = []
        floor_num = geometry.floor_number

        habitable_rooms = [r for r in geometry.rooms if not r.is_corridor]
        all_rooms = geometry.rooms

        room_by_id = {r.id: r for r in all_rooms}
        wall_map = {w.id: w for w in geometry.walls}

        # Build adjacency graph: room_id -> set of connected room_ids
        graph: Dict[str, Set[str]] = {r.id: set() for r in all_rooms}
        graph["exterior"] = set()

        entrance_room_ids: Set[str] = set()

        for door in geometry.doors:
            wall = wall_map.get(door.wall_id)
            if not wall:
                continue

            if door.type in {"entrance", "exterior"} or door.connects_to == "exterior":
                # Connects exterior to room(s) on the wall
                for rid in wall.room_ids:
                    if rid in graph:
                        graph["exterior"].add(rid)
                        graph[rid].add("exterior")
                        if door.type == "entrance":
                            entrance_room_ids.add(rid)

            else:
                # Interior door connecting rooms on the wall
                if len(wall.room_ids) >= 2:
                    r1, r2 = wall.room_ids[0], wall.room_ids[1]
                    if r1 in graph and r2 in graph:
                        graph[r1].add(r2)
                        graph[r2].add(r1)
                elif len(wall.room_ids) == 1:
                    # Single room wall - check if door specifies target room
                    r1 = wall.room_ids[0]
                    # Find target room by connects_to
                    for r in all_rooms:
                        if (
                            r.id == door.connects_to
                            or r.room_type == door.connects_to
                            or r.architectural_room_id == door.connects_to
                            or (door.connects_to in ("circulation", "corridor", "hallway") and r.is_corridor)
                        ):
                            graph[r1].add(r.id)
                            graph[r.id].add(r1)
                            break

        # 1. Check for completely isolated rooms (zero connecting doors)
        for room in habitable_rooms:
            connected_neighbors = graph.get(room.id, set())
            if not connected_neighbors:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="connectivity",
                        check="isolated_room",
                        message=f"Room '{room.room_type}' (id={room.id}) is physically isolated with no connecting doors",
                        target_id=room.id,
                        room_id=room.id,
                        floor_number=floor_num,
                    )
                )

        # 2. On Floor 1, verify entrance reachability
        if floor_num == 1:
            if not entrance_room_ids:
                # Check if an entrance door was found in graph["exterior"]
                if graph["exterior"]:
                    entrance_room_ids = set(graph["exterior"])

            if not entrance_room_ids:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        category="connectivity",
                        check="missing_entrance_connection",
                        message="Floor 1 has no physical entrance door connecting the exterior to the interior",
                        floor_number=1,
                    )
                )
            else:
                # BFS reachability from entrance
                visited: Set[str] = set()
                queue = deque(list(entrance_room_ids))
                visited.update(entrance_room_ids)

                while queue:
                    curr = queue.popleft()
                    for neighbor in graph.get(curr, set()):
                        if neighbor != "exterior" and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                # Check if primary social spaces (living / dining / corridor) are reached
                unreached_social = [
                    r for r in habitable_rooms
                    if r.room_type in {"living", "dining", "hall", "drawing"} and r.id not in visited
                ]
                for ur in unreached_social:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            category="connectivity",
                            check="unreachable_from_entrance",
                            message=f"Primary social room '{ur.room_type}' (id={ur.id}) cannot be reached from the main entrance",
                            target_id=ur.id,
                            room_id=ur.id,
                            floor_number=1,
                        )
                    )

        return issues
