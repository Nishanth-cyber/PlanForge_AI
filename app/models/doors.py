"""Door intent models for architectural proposals.

DoorIntent represents the architectural decision of where doors should exist
and what spaces they connect (HOW).
Detailed door geometry (exact position, cutouts, swing arcs) is constructed
by the Geometry Engine as GeoDoor (in app.models.geometry).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class DoorIntent:
    """Architectural proposal for a door connecting spaces."""
    id: str = field(default_factory=generate_id)
    connects_from: str = ""  # Room ID or room type
    connects_to: str = ""  # Room ID, room type, or "exterior"
    wall_orientation: Optional[str] = None  # e.g. "north", "south", "east", "west"
    door_type: str = "interior"  # "interior", "exterior", "entrance", "balcony", "pocket"
    recommended_width: float = 0.9
    recommended_height: float = 2.1
    floor_number: int = 1
    rationale: str = ""


# Backward-compatible alias
DoorSpec = DoorIntent
