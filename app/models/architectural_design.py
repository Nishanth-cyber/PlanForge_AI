"""Architectural design models for the LLM Architectural Designer.

The Architectural Design represents HOW spaces are shaped, connected, and accessed:
- Room shapes, dimensions, and proportions within allocated ASAA regions
- Door placement intents connecting functional spaces
- Window placement intents for daylight and ventilation
- Staircase placement intents for multi-floor connectivity
- Architectural design rationales

Detailed geometric construction (wall buffers, exact door swing arcs, coordinate
snapping) is handled downstream by the Geometry Engine (in app.models.geometry).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id
from app.models.doors import DoorIntent
from app.models.windows import WindowIntent
from app.models.staircase import StaircaseIntent

# Backward-compatible aliases
Door = DoorIntent
Window = WindowIntent


@dataclass
class RoomDesign:
    """An architectural room design proposal within an ASAA allocated region."""
    id: str = field(default_factory=generate_id)
    room_type: str = ""
    allocated_region_id: Optional[str] = None  # Reference to ASAA AllocatedRegion
    floor_number: int = 1
    intended_shape: str = "rectangular"  # "rectangular", "l_shaped", "custom"
    intended_dimensions: Optional[tuple[float, float]] = None  # (width, length) in meters
    intended_area_sqm: float = 0.0
    proposed_boundary: list[tuple[float, float]] = field(default_factory=list)  # Suggested room boundary
    doors: list[DoorIntent] = field(default_factory=list)  # Door intents associated with this room
    windows: list[WindowIntent] = field(default_factory=list)  # Window intents associated with this room
    connected_spaces: list[str] = field(default_factory=list)  # Target connected room types/IDs
    design_rationale: str = ""


# Alias for explicit clarity
RoomDesignProposal = RoomDesign


@dataclass
class ArchitecturalDesign:
    """Complete architectural design proposal for a single floor."""
    id: str = field(default_factory=generate_id)
    floor_number: int = 1
    floor_name: str = ""
    rooms: list[RoomDesign] = field(default_factory=list)
    circulation_corridors: list[dict] = field(default_factory=list)  # Proposed corridor shapes/paths
    staircase_intent: Optional[StaircaseIntent] = None
    allocation_id: Optional[str] = None  # Reference to ASAA Allocation
    design_rationale: str = ""
    metadata: dict = field(default_factory=dict)
    version: int = 0

    def get_room(self, room_id: str) -> Optional[RoomDesign]:
        """Find a room design proposal by ID."""
        for r in self.rooms:
            if r.id == room_id:
                return r
        return None

    def get_rooms_by_type(self, room_type: str) -> list[RoomDesign]:
        """Find all room design proposals of a specific type."""
        return [r for r in self.rooms if r.room_type == room_type]

    def all_door_intents(self) -> list[DoorIntent]:
        """Collect all door intents across all rooms in this floor design."""
        doors: list[DoorIntent] = []
        for r in self.rooms:
            doors.extend(r.doors)
        return doors

    def all_window_intents(self) -> list[WindowIntent]:
        """Collect all window intents across all rooms in this floor design."""
        windows: list[WindowIntent] = []
        for r in self.rooms:
            windows.extend(r.windows)
        return windows


@dataclass
class ArchitecturalDesignSet:
    """Complete architectural design proposal across all floors."""
    id: str = field(default_factory=generate_id)
    designs: list[ArchitecturalDesign] = field(default_factory=list)
    allocation_set_id: Optional[str] = None
    version: int = 0

    def get_design(self, floor_number: int) -> Optional[ArchitecturalDesign]:
        """Retrieve the architectural design for a specific floor."""
        for d in self.designs:
            if d.floor_number == floor_number:
                return d
        return None
