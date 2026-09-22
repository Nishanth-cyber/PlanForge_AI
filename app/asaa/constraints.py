"""ASAA constraint definitions."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Constraint:
    """Base constraint."""
    name: str = ""
    weight: float = 1.0
    description: str = ""


@dataclass
class AreaConstraint(Constraint):
    """Constraint on area."""
    min_area_sqm: Optional[float] = None
    max_area_sqm: Optional[float] = None


@dataclass
class AdjacencyConstraint(Constraint):
    """Constraint on adjacency between room types."""
    room_type_a: str = ""
    room_type_b: str = ""
    required: bool = True


@dataclass
class AspectRatioConstraint(Constraint):
    """Constraint on aspect ratio."""
    min_ratio: float = 0.5
    max_ratio: float = 2.0


@dataclass
class CirculationConstraint(Constraint):
    """Constraint on circulation space."""
    min_area_sqm: float = 0.0


@dataclass
class BoundaryConstraint(Constraint):
    """Constraint on boundary containment."""
    plot_polygon: list[tuple[float, float]] = None
