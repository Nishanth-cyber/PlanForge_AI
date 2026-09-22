"""Requirement models for the PlanForge pipeline.

Requirements represent WHAT the user wants.
They do NOT contain final room geometry, detailed wall positions, or invented requirements.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class RoomRequirement:
    """A single room requirement specified by the user or derived explicitly."""
    id: str = field(default_factory=generate_id)
    room_type: str = ""
    min_count: int = 1
    max_count: Optional[int] = None
    min_area_sqm: Optional[float] = None
    max_area_sqm: Optional[float] = None
    preferred_area_sqm: Optional[float] = None
    target_area_sqm: Optional[float] = None  # Alias / synonym for preferred_area_sqm
    adjacency: list[str] = field(default_factory=list)
    separation: list[str] = field(default_factory=list)  # Rooms that should be kept separate/avoided
    attached_to: Optional[str] = None  # e.g. attached bathroom linked to master bedroom
    user_dimensions: Optional[tuple[float, float]] = None  # (width_m, length_m) if explicitly specified by user
    description: str = ""
    source: str = "user"  # "user", "derived", "default"

    def __post_init__(self) -> None:
        if self.user_dimensions is not None:
            w, l = self.user_dimensions
            calc_area = round(float(w) * float(l), 2)
            if self.preferred_area_sqm is None and self.target_area_sqm is None:
                self.preferred_area_sqm = calc_area
                self.target_area_sqm = calc_area

        if self.target_area_sqm is not None and self.preferred_area_sqm is None:
            self.preferred_area_sqm = self.target_area_sqm
        elif self.preferred_area_sqm is not None and self.target_area_sqm is None:
            self.target_area_sqm = self.preferred_area_sqm



@dataclass
class FloorRequirement:
    """Requirements for a specific floor."""
    id: str = field(default_factory=generate_id)
    floor_number: int = 1
    floor_name: str = ""
    total_area_sqm: Optional[float] = None
    room_requirements: list[RoomRequirement] = field(default_factory=list)
    circulation_required: bool = True
    staircase_required: bool = False
    description: str = ""
    source: str = "user"

    def total_rooms(self) -> int:
        """Total minimum rooms required on this floor."""
        return sum(r.min_count for r in self.room_requirements)


FloorRequirements = FloorRequirement


@dataclass
class Requirements:
    """Complete set of user-specified requirements."""
    id: str = field(default_factory=generate_id)
    project_name: str = ""
    plot_area_sqm: Optional[float] = None
    plot_dimensions: Optional[tuple[float, float]] = None  # (width, depth) in meters
    plot_shape: Optional[tuple[tuple[float, float], ...]] = None  # Boundary polygon vertices
    setbacks: dict[str, float] = field(default_factory=dict)  # e.g. {"front": 3.0, "rear": 2.0, "left": 1.5, "right": 1.5}
    orientation: Optional[str] = None  # Primary plot orientation ("north", "south", "east", "west")
    entrance_facing: Optional[str] = None  # Facing direction of main entrance
    entrance_room_type: Optional[str] = None  # Preferred room connecting to entrance (e.g. "living", "foyer")
    target_floors: Optional[int] = None
    floors: list[FloorRequirement] = field(default_factory=list)
    floor_requirements: Optional[list[FloorRequirement]] = None
    notes: str = ""
    raw_input: str = ""

    def __post_init__(self) -> None:
        if self.floor_requirements is not None and not self.floors:
            self.floors = self.floor_requirements
        elif self.floor_requirements is None:
            self.floor_requirements = self.floors

    def get_floor(self, floor_number: int) -> Optional[FloorRequirement]:
        """Retrieve requirements for a specific floor number."""
        for f in self.floors:
            if f.floor_number == floor_number:
                return f
        return None

    get_floor_requirements = get_floor

    def total_rooms(self) -> int:
        """Total minimum rooms required across all floors."""
        return sum(f.total_rooms() for f in self.floors)

    def has_requirements_for_floor(self, floor_number: int) -> bool:
        """Check whether explicit room requirements exist for a floor."""
        f = self.get_floor(floor_number)
        if f is None:
            return False
        return len(f.room_requirements) > 0

    def all_room_requirements(self) -> list[RoomRequirement]:
        """Get flattened list of all room requirements across all floors."""
        result = []
        for f in self.floors:
            result.extend(f.room_requirements)
        return result
