"""Window intent models for architectural proposals.

WindowIntent represents the architectural decision of where windows should exist,
which wall/orientation they occupy, and sizing recommendations (HOW).
Detailed window geometry and openings are constructed by the Geometry Engine as
GeoWindow (in app.models.geometry).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from app.utils.ids import generate_id


@dataclass
class WindowIntent:
    """Architectural proposal for a window providing daylight/ventilation."""
    id: str = field(default_factory=generate_id)
    room_id: str = ""  # Room ID or room type receiving natural light
    wall_orientation: str = ""  # e.g. "north", "south", "east", "west"
    window_type: str = "standard"  # "standard", "bay", "skylight", "ventilation"
    recommended_width: float = 1.2
    recommended_height: float = 1.2
    sill_height: float = 0.9
    floor_number: int = 1
    rationale: str = ""


# Backward-compatible alias
WindowSpec = WindowIntent
