"""ASAA data models."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class SpatialCell:
    """A cell in the spatial grid."""
    id: str = field(default_factory=generate_id)
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    occupied_by: Optional[str] = None


@dataclass
class SpatialRegion:
    """A spatial region."""
    id: str = field(default_factory=generate_id)
    room_type: str = ""
    polygon: list[tuple[float, float]] = field(default_factory=list)
    area_sqm: float = 0.0
    centroid: Optional[tuple[float, float]] = None
    cells: list[str] = field(default_factory=list)


@dataclass
class ASAAConfig:
    """Configuration for ASAA."""
    grid_size: float = 1.0
    max_iterations: int = 1000
    seed: int = 42
    min_room_area_sqm: float = 6.0
    min_corridor_width: float = 1.0
    min_clearance_sqm: float = 1.0
