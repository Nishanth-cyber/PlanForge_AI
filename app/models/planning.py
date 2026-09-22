"""Planning models for the PlanForge pipeline.

Planning models represent strategic planning decisions derived from requirements.
They do NOT contain final room polygons or detailed door/window geometry.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


class IncompleteRequirementsError(ValueError):
    """Raised when planning is requested on incomplete or invalid requirements."""
    pass


@dataclass
class RoomSpec:
    """A room specification in the planning output."""
    id: str = field(default_factory=generate_id)
    room_type: str = ""
    room_category: str = "social"  # "private", "social", "service", "circulation", "outdoor", "other"
    floor_number: int = 1
    count: int = 1
    target_area_sqm: float = 0.0
    min_area_sqm: Optional[float] = None
    max_area_sqm: Optional[float] = None
    adjacency: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)  # Types of rooms this room should NOT touch
    attached_to_room_id: Optional[str] = None  # Direct parent/attached room ID if any (e.g. ensuite)
    user_dimensions: Optional[tuple[float, float]] = None  # (width_m, length_m) if specified by user
    priority: str = "normal"  # "high", "normal", "low"

    priority_rationale: str = ""  # Explainability rationale for the priority assignment
    original_name: str = ""  # User's original phrasing or label before categorization
    source_requirement_id: Optional[str] = None


@dataclass
class FloorPlanSpec:
    """Planning specification for a single floor."""
    id: str = field(default_factory=generate_id)
    floor_number: int = 1
    floor_name: str = ""
    total_area_sqm: Optional[float] = None
    room_specs: list[RoomSpec] = field(default_factory=list)
    circulation_zones: list[str] = field(default_factory=list)
    circulation_notes: str = ""
    adjacency_matrix: dict[str, list[str]] = field(default_factory=dict)
    avoid_matrix: dict[str, list[str]] = field(default_factory=dict)
    entrance_intent: Optional[dict] = None  # e.g. {"preferred_room": "living", "facing": "east"}
    staircase_intent: Optional[dict] = None  # e.g. {"required": True, "connects_floors": [1, 2]}


@dataclass
class PlanningSpec:
    """Complete planning specification derived from requirements."""
    id: str = field(default_factory=generate_id)
    project_name: str = ""
    floors: list[FloorPlanSpec] = field(default_factory=list)
    global_constraints: dict = field(default_factory=dict)
    source_requirements_id: Optional[str] = None

    def get_floor(self, floor_number: int) -> Optional[FloorPlanSpec]:
        """Retrieve the planning specification for a given floor."""
        for f in self.floors:
            if f.floor_number == floor_number:
                return f
        return None

    get_floor_spec = get_floor

    def all_room_specs(self) -> list[RoomSpec]:
        """Retrieve a flattened list of all room specs across all floors."""
        result = []
        for f in self.floors:
            result.extend(f.room_specs)
        return result

    def get_room_by_id(self, room_id: str) -> Optional[RoomSpec]:
        """Find a room specification by its unique ID."""
        for r in self.all_room_specs():
            if r.id == room_id:
                return r
        return None

    def total_target_area(self) -> float:
        """Calculate total target area summed across all planned rooms."""
        return sum(r.target_area_sqm * r.count for r in self.all_room_specs())
