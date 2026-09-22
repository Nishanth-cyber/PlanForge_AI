"""Geometry models for deterministic geometric representation.

Geometry represents CONSTRUCT:
- Exact constructed walls, footprints, and wall polygons
- Usable interior polygons and built exterior room boundaries
- Constructed door openings and swing arc geometry
- Constructed window openings and sill geometry
- Constructed staircase treads, risers, and footprint polygons

Geometry models do NOT make architectural decisions; they deterministically
realize the proposals from ArchitecturalDesign.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class GeoWall:
    """A constructed wall segment."""
    id: str = field(default_factory=generate_id)
    start: tuple[float, float] = (0.0, 0.0)
    end: tuple[float, float] = (0.0, 0.0)
    thickness: float = 0.2
    height: float = 3.0
    type: str = "interior"  # "interior", "exterior", "partition", "boundary"
    floor_number: int = 1
    polygon: list[tuple[float, float]] = field(default_factory=list)  # 2D wall footprint polygon
    room_ids: list[str] = field(default_factory=list)  # Associated room IDs


@dataclass
class GeoDoor:
    """A constructed door with exact wall placement and swing geometry."""
    id: str = field(default_factory=generate_id)
    wall_id: str = ""
    position: tuple[float, float] = (0.0, 0.0)
    width: float = 0.9
    height: float = 2.1
    type: str = "interior"
    connects_from: str = ""
    connects_to: str = ""
    swing_arc: Optional[list[tuple[float, float]]] = None  # Constructed swing arc polygon vertices
    floor_number: int = 1
    intent_id: Optional[str] = None  # Reference to upstream DoorIntent


@dataclass
class GeoWindow:
    """A constructed window opening."""
    id: str = field(default_factory=generate_id)
    wall_id: str = ""
    position: tuple[float, float] = (0.0, 0.0)
    width: float = 1.2
    height: float = 1.2
    sill_height: float = 0.9
    type: str = "standard"
    floor_number: int = 1
    intent_id: Optional[str] = None  # Reference to upstream WindowIntent


@dataclass
class GeoStaircase:
    """A constructed staircase with treads and risers."""
    id: str = field(default_factory=generate_id)
    polygon: list[tuple[float, float]] = field(default_factory=list)  # Footprint polygon
    from_floor: int = 1
    to_floor: int = 2
    width: float = 1.0
    depth: float = 0.3
    riser_count: int = 16
    tread_depth: float = 0.28
    floor_number: int = 1
    intent_id: Optional[str] = None  # Reference to upstream StaircaseIntent


@dataclass
class GeoRoom:
    """A constructed room with dual usable and built polygons."""
    id: str = field(default_factory=generate_id)
    room_type: str = ""
    usable_polygon: list[tuple[float, float]] = field(default_factory=list)  # Interior usable area
    built_polygon: list[tuple[float, float]] = field(default_factory=list)  # Exterior wall centerline/outer
    area_sqm: float = 0.0
    walls: list[str] = field(default_factory=list)  # Associated GeoWall IDs
    doors: list[str] = field(default_factory=list)  # Associated GeoDoor IDs
    windows: list[str] = field(default_factory=list)  # Associated GeoWindow IDs
    floor_number: int = 1
    architectural_room_id: Optional[str] = None  # Reference to upstream RoomDesign
    is_corridor: bool = False

    # Backward-compatible property
    @property
    def polygon(self) -> list[tuple[float, float]]:
        """Return usable polygon as default geometry representation."""
        return self.usable_polygon or self.built_polygon


@dataclass
class Geometry:
    """Complete constructed geometric representation of a single floor."""
    id: str = field(default_factory=generate_id)
    floor_number: int = 1
    rooms: list[GeoRoom] = field(default_factory=list)
    walls: list[GeoWall] = field(default_factory=list)
    doors: list[GeoDoor] = field(default_factory=list)
    windows: list[GeoWindow] = field(default_factory=list)
    staircases: list[GeoStaircase] = field(default_factory=list)
    plot_polygon: list[tuple[float, float]] = field(default_factory=list)
    buildable_polygon: list[tuple[float, float]] = field(default_factory=list)

    def get_room(self, room_id: str) -> Optional[GeoRoom]:
        """Find a constructed room by ID."""
        for r in self.rooms:
            if r.id == room_id:
                return r
        return None

    def get_wall(self, wall_id: str) -> Optional[GeoWall]:
        """Find a constructed wall by ID."""
        for w in self.walls:
            if w.id == wall_id:
                return w
        return None

    def get_door(self, door_id: str) -> Optional[GeoDoor]:
        """Find a constructed door by ID."""
        for d in self.doors:
            if d.id == door_id:
                return d
        return None

    def total_usable_area(self) -> float:
        """Sum of usable areas across all rooms on this floor."""
        return sum(r.area_sqm for r in self.rooms)


@dataclass
class GeometrySet:
    """Complete constructed geometric representation across all floors."""
    id: str = field(default_factory=generate_id)
    geometries: list[Geometry] = field(default_factory=list)
    architectural_design_id: Optional[str] = None

    def get_geometry(self, floor_number: int) -> Optional[Geometry]:
        """Retrieve geometry for a specific floor."""
        for g in self.geometries:
            if g.floor_number == floor_number:
                return g
        return None
