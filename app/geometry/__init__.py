"""Geometry Engine package for PlanForge AI.

Deterministic construction of physical CAD-ready architectural geometry.
"""

from app.geometry.corridor_builder import CorridorBuilder
from app.geometry.door_builder import DoorBuilder
from app.geometry.engine import GeometryEngine
from app.geometry.exceptions import (
    CorridorConstructionError,
    DoorPlacementError,
    GeometryConstructionError,
    ImpossibleDimensionsError,
    InvalidRoomGeometryError,
    InvalidShapeParametersError,
    RoomOutOfBoundsError,
    StaircaseConstructionError,
    WindowPlacementError,
)
from app.geometry.polygon_builder import PolygonBuilder
from app.geometry.room_builder import RoomBuilder
from app.geometry.staircase_builder import StaircaseBuilder
from app.geometry.wall_builder import WallBuilder
from app.geometry.window_builder import WindowBuilder

__all__ = [
    "GeometryEngine",
    "PolygonBuilder",
    "RoomBuilder",
    "WallBuilder",
    "DoorBuilder",
    "WindowBuilder",
    "StaircaseBuilder",
    "CorridorBuilder",
    "GeometryConstructionError",
    "InvalidRoomGeometryError",
    "RoomOutOfBoundsError",
    "ImpossibleDimensionsError",
    "InvalidShapeParametersError",
    "DoorPlacementError",
    "WindowPlacementError",
    "StaircaseConstructionError",
    "CorridorConstructionError",
]
