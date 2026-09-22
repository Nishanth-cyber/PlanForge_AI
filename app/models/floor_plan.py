"""Floor plan models combining all pipeline outputs.

FloorPlan and FloorPlanSet represent the final aggregated output:
- Plot and buildable boundaries
- Constructed geometries per floor
- Authoritative validation results and scores
- Generation metadata and provenance
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id
from app.models.geometry import Geometry
from app.models.validation import ValidationResult, ValidationReport


@dataclass
class FloorPlan:
    """Complete validated floor plan for a single floor."""
    id: str = field(default_factory=generate_id)
    project_name: str = ""
    floor_number: int = 1
    geometry: Optional[Geometry] = None
    validation: Optional[ValidationResult] = None
    is_valid: bool = False
    metadata: dict = field(default_factory=dict)
    notes: str = ""

    def usable_area(self) -> float:
        """Total usable interior area for this floor."""
        if self.geometry:
            return self.geometry.total_usable_area()
        return 0.0


@dataclass
class FloorPlanSet:
    """Complete validated multi-floor plan set.

    Explicitly maintains per-floor separation to prevent ambiguous
    Floor-1-only mirroring bugs.
    """
    id: str = field(default_factory=generate_id)
    project_name: str = ""
    plot_boundary: list[tuple[float, float]] = field(default_factory=list)
    buildable_boundary: list[tuple[float, float]] = field(default_factory=list)
    floor_plans: list[FloorPlan] = field(default_factory=list)
    validation_report: Optional[ValidationReport] = None
    generation_metadata: dict = field(default_factory=dict)

    def get_floor_plan(self, floor_number: int) -> Optional[FloorPlan]:
        """Retrieve the floor plan for a specific floor number."""
        for fp in self.floor_plans:
            if fp.floor_number == floor_number:
                return fp
        return None

    @property
    def all_valid(self) -> bool:
        """Check whether every floor plan in the set passed validation."""
        if not self.floor_plans:
            return False
        return all(fp.is_valid for fp in self.floor_plans)

    @property
    def total_usable_area(self) -> float:
        """Sum of usable areas across all floors."""
        return sum(fp.usable_area() for fp in self.floor_plans)
