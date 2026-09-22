"""Circulation Planner — plans circulation, entrance, and vertical access intents.

Represents circulation and accessibility requirements WITHOUT constructing physical corridor,
door, or staircase geometry.
"""

from __future__ import annotations

from typing import Optional
from app.models.planning import RoomSpec


class CirculationPlanner:
    """Derives circulation zones, entrance intent, and staircase intent."""

    @staticmethod
    def plan_circulation_zones(
        floor_number: int,
        room_specs: list[RoomSpec],
        is_multi_floor: bool,
    ) -> tuple[list[str], str]:
        """Identify required circulation zones and notes for a floor.

        Zones include:
        - 'public_circulation': between entrance, living, dining
        - 'private_circulation': between bedrooms, bathrooms, quiet spaces
        - 'vertical_circulation': staircase lobby linking floors
        - 'service_circulation': utility, kitchen, exterior access
        """
        zones: list[str] = []
        categories = {r.room_category for r in room_specs}

        if "social" in categories or floor_number == 1:
            zones.append("public_circulation")

        if "private" in categories:
            zones.append("private_circulation")

        if "service" in categories:
            zones.append("service_circulation")

        if is_multi_floor:
            zones.append("vertical_circulation")

        notes_parts = []
        if "public_circulation" in zones:
            notes_parts.append("Direct accessible flow between primary social spaces.")
        if "private_circulation" in zones:
            notes_parts.append("Acoustic and visual buffering for private sleeping spaces.")
        if "vertical_circulation" in zones:
            notes_parts.append("Clear unimpeded access to vertical staircase core.")

        notes = " ".join(notes_parts)
        return zones, notes

    @staticmethod
    def plan_entrance_intent(
        floor_number: int,
        orientation: Optional[str] = None,
        entrance_facing: Optional[str] = None,
        entrance_room_type: Optional[str] = None,
    ) -> Optional[dict]:
        """Create entrance intent specification for Floor 1."""
        if floor_number != 1:
            return None

        facing = entrance_facing or orientation or "north"
        target = entrance_room_type or "living"

        return {
            "facing": facing,
            "preferred_room": target,
            "access_type": "primary_entrance",
            "intent_description": f"Primary entrance facing {facing} opening into {target}.",
        }

    @staticmethod
    def plan_staircase_intent(
        floor_number: int,
        total_floors: int,
        staircase_required: bool,
    ) -> Optional[dict]:
        """Create vertical circulation intent for staircase connectivity."""
        if total_floors <= 1 and not staircase_required:
            return None

        connects = list(range(1, total_floors + 1))
        return {
            "required": True,
            "connects_floors": connects,
            "current_floor": floor_number,
            "role": "vertical_access_core",
            "alignment_required": True,  # Critical for ASAA vertical alignment
            "intent_description": f"Vertical core connecting floors {connects}.",
        }
