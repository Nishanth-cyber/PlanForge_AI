"""Structured exception hierarchy for the Geometry Engine.

The Geometry Engine is a deterministic construction layer. When architectural
proposals violate physical bounds or cannot be realized geometrically, the engine
raises structured exceptions rather than silently redesigning the layout.
"""

from __future__ import annotations


class GeometryConstructionError(Exception):
    """Base exception for all geometry construction errors."""
    pass


class InvalidRoomGeometryError(GeometryConstructionError):
    """Raised when a constructed room polygon is degenerate, self-intersecting, or has non-positive area."""
    pass


class RoomOutOfBoundsError(GeometryConstructionError):
    """Raised when a room design extends outside its assigned ASAA allocated region."""
    pass


class ImpossibleDimensionsError(GeometryConstructionError):
    """Raised when specified dimensions cannot fit geometrically within the allocated region."""
    pass


class InvalidShapeParametersError(GeometryConstructionError):
    """Raised when shape-specific parameters (e.g. L-shape cutout or leg widths) are invalid."""
    pass


class DoorPlacementError(GeometryConstructionError):
    """Raised when a DoorIntent cannot be physically placed on any suitable wall."""
    pass


class WindowPlacementError(GeometryConstructionError):
    """Raised when a WindowIntent cannot be placed on any suitable exterior wall."""
    pass


class StaircaseConstructionError(GeometryConstructionError):
    """Raised when a staircase cannot be constructed within its allocated core."""
    pass


class CorridorConstructionError(GeometryConstructionError):
    """Raised when circulation geometry cannot be constructed."""
    pass
