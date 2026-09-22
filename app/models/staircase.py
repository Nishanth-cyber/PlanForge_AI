"""Staircase intent models for architectural proposals.

StaircaseIntent represents the architectural decision of where vertical circulation
occurs, which floors it connects, and intended stair typology (HOW).
Detailed staircase geometry (treads, risers, exact polygon, landing) is constructed
by the Geometry Engine as GeoStaircase (in app.models.geometry).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class StaircaseIntent:
    """Architectural proposal for vertical staircase circulation."""
    id: str = field(default_factory=generate_id)
    from_floor: int = 1
    to_floor: int = 2
    stair_type: str = "straight"  # "straight", "l_shaped", "u_shaped", "spiral"
    approx_location: Optional[tuple[float, float]] = None  # Approximate (x, y) anchor
    allocated_region_id: Optional[str] = None
    recommended_width: float = 1.0
    connects_to_rooms: list[str] = field(default_factory=list)
    floor_number: int = 1
    rationale: str = ""


# Backward-compatible alias
StaircaseSpec = StaircaseIntent
