"""Allocation models for the ASAA engine.

ASAA allocation represents WHERE:
- Spatial partitioning and allocated regions per room/space
- Approximate spatial bounding regions and relative positions
- Circulation zones and vertical stair zones

ASAA allocation does NOT contain final architectural geometry, doors, windows,
or detailed wall construction.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class AllocatedRegion:
    """A spatial region allocated to a room or functional zone by ASAA."""
    id: str = field(default_factory=generate_id)
    room_type: str = ""
    room_spec_id: Optional[str] = None
    floor_number: int = 1
    target_area_sqm: float = 0.0
    area_sqm: float = 0.0
    approximate_dimensions: Optional[tuple[float, float]] = None  # (width, length) in meters
    polygon: list[tuple[float, float]] = field(default_factory=list)  # 2D boundary polygon of the region
    centroid: Optional[tuple[float, float]] = None
    priority: str = "normal"  # "high", "normal", "low"
    adjacency_regions: list[str] = field(default_factory=list)  # IDs of adjacent allocated regions
    zone_type: str = "room"  # "room", "circulation", "entrance", "staircase"
    score: float = 0.0


@dataclass
class Allocation:
    """Complete allocation result from ASAA for a single floor."""
    id: str = field(default_factory=generate_id)
    floor_number: int = 1
    floor_name: str = ""
    total_area_sqm: float = 0.0
    allocated_regions: list[AllocatedRegion] = field(default_factory=list)
    circulation_area_sqm: float = 0.0
    score: float = 0.0
    algorithm_version: str = "1.0"

    def get_region_by_id(self, region_id: str) -> Optional[AllocatedRegion]:
        """Find an allocated region by its ID."""
        for r in self.allocated_regions:
            if r.id == region_id:
                return r
        return None

    def get_regions_by_type(self, room_type: str) -> list[AllocatedRegion]:
        """Find all allocated regions matching a room type."""
        return [r for r in self.allocated_regions if r.room_type == room_type]

    def get_circulation_regions(self) -> list[AllocatedRegion]:
        """Find all regions tagged as circulation space."""
        return [r for r in self.allocated_regions if r.zone_type == "circulation"]

    def get_staircase_region(self) -> Optional[AllocatedRegion]:
        """Find the staircase region if one exists on this floor."""
        for r in self.allocated_regions:
            if r.zone_type == "staircase" or r.room_type == "staircase":
                return r
        return None

    def get_entrance_region(self) -> Optional[AllocatedRegion]:
        """Find the primary entrance region if one exists on this floor."""
        for r in self.allocated_regions:
            if r.zone_type == "entrance":
                return r
        return None


@dataclass
class AllocationSet:
    """Complete allocation across all floors."""
    id: str = field(default_factory=generate_id)
    allocations: list[Allocation] = field(default_factory=list)
    planning_spec_id: Optional[str] = None
    staircase_aligned: bool = False  # Confirmed vertical alignment of staircase region

    def get_allocation(self, floor_number: int) -> Optional[Allocation]:
        """Retrieve allocation for a specific floor."""
        for a in self.allocations:
            if a.floor_number == floor_number:
                return a
        return None

    def total_score(self) -> float:
        """Calculate average allocation score across all floors."""
        if not self.allocations:
            return 0.0
        return sum(a.score for a in self.allocations) / len(self.allocations)
