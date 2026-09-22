"""ASAA exceptions."""

from __future__ import annotations
from typing import Optional


class InfeasibleAllocationError(ValueError):
    """Raised when spatial allocation cannot satisfy room area or boundary constraints.
    
    Indicates that the buildable area is insufficient to accommodate the minimum
    required room areas plus required circulation allowance.
    """

    def __init__(
        self,
        message: str,
        available_area_sqm: float = 0.0,
        requested_min_area_sqm: float = 0.0,
        deficit_sqm: float = 0.0,
        offending_rooms: Optional[list[str]] = None,
        floor_number: int = 1,
    ):
        super().__init__(message)
        self.available_area_sqm = available_area_sqm
        self.requested_min_area_sqm = requested_min_area_sqm
        self.deficit_sqm = deficit_sqm
        self.offending_rooms = offending_rooms or []
        self.floor_number = floor_number


class BoundaryConstraintError(ValueError):
    """Raised when plot boundary or setback specifications are geometrically invalid."""

    def __init__(self, message: str, plot_polygon: Optional[list[tuple[float, float]]] = None):
        super().__init__(message)
        self.plot_polygon = plot_polygon or []
