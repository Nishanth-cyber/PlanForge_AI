"""Requirement Validator — performs semantic and sanity checks on structured Requirements.

Ensures requirements are logically valid before passing to the Planning Agent:
- Positive plot dimensions and areas.
- Consistent area ranges (min_area <= preferred_area <= max_area).
- Positive room counts (min_count >= 1, max_count >= min_count).
- Valid sequential floor numbers.
- Valid relationship constraints (no self-adjacency, no self-separation, no conflicting adjacency+avoidance).
- Valid orientations and entrance facing directions.
- Multi-floor staircase consistency.

Does NOT perform geometric validation (wall alignment, polygon containment, door swing).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.agents.requirement_agent.normalizer import CARDINAL_DIRECTIONS


@dataclass
class RequirementValidationIssue:
    """A semantic issue found during requirement validation."""
    severity: str  # "error", "warning"
    field: str
    message: str
    floor_number: Optional[int] = None
    room_type: Optional[str] = None


@dataclass
class RequirementValidationResult:
    """Result of requirement validation."""
    is_valid: bool
    issues: list[RequirementValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[RequirementValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[RequirementValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def add_error(self, field_name: str, message: str, floor: Optional[int] = None, room: Optional[str] = None) -> None:
        self.issues.append(RequirementValidationIssue(
            severity="error",
            field=field_name,
            message=message,
            floor_number=floor,
            room_type=room,
        ))
        self.is_valid = False

    def add_warning(self, field_name: str, message: str, floor: Optional[int] = None, room: Optional[str] = None) -> None:
        self.issues.append(RequirementValidationIssue(
            severity="warning",
            field=field_name,
            message=message,
            floor_number=floor,
            room_type=room,
        ))


class RequirementValidator:
    """Performs semantic validation on structured Requirements."""

    def validate(self, requirements: Requirements) -> RequirementValidationResult:
        """Validate the Requirements instance."""
        result = RequirementValidationResult(is_valid=True)

        # 1. Plot validation
        self._validate_plot(requirements, result)

        # 2. Orientation & Entrance validation
        self._validate_orientation(requirements, result)

        # 3. Floors & Rooms validation
        self._validate_floors_and_rooms(requirements, result)

        return result

    def _validate_plot(self, reqs: Requirements, res: RequirementValidationResult) -> None:
        if reqs.plot_dimensions is not None:
            w, d = reqs.plot_dimensions
            if w <= 0:
                res.add_error("plot_dimensions", f"Plot width must be positive, got {w}m")
            if d <= 0:
                res.add_error("plot_dimensions", f"Plot depth must be positive, got {d}m")
            if w > 0 and d > 0:
                ratio = w / d
                if ratio < 0.05 or ratio > 20.0:
                    res.add_warning("plot_dimensions", f"Extreme plot aspect ratio ({ratio:.2f})")

        if reqs.plot_area_sqm is not None and reqs.plot_area_sqm <= 0:
            res.add_error("plot_area_sqm", f"Plot area must be positive, got {reqs.plot_area_sqm} sqm")

        # Setback checks
        if reqs.setbacks:
            for side, val in reqs.setbacks.items():
                if val < 0:
                    res.add_error(f"setbacks.{side}", f"Setback for {side} cannot be negative ({val}m)")

            if reqs.plot_dimensions:
                w, d = reqs.plot_dimensions
                front = reqs.setbacks.get("front", 0.0)
                rear = reqs.setbacks.get("rear", 0.0)
                left = reqs.setbacks.get("left", 0.0)
                right = reqs.setbacks.get("right", 0.0)
                side_val = reqs.setbacks.get("side", 0.0)
                effective_lr = (left + right) if (left or right) else (side_val * 2)

                if (front + rear) >= d:
                    res.add_error("setbacks", f"Combined front and rear setbacks ({front + rear}m) exceed or equal plot depth ({d}m)")
                if effective_lr >= w:
                    res.add_error("setbacks", f"Combined side setbacks ({effective_lr}m) exceed or equal plot width ({w}m)")

    def _validate_orientation(self, reqs: Requirements, res: RequirementValidationResult) -> None:
        if reqs.orientation is not None:
            if reqs.orientation.lower() not in CARDINAL_DIRECTIONS:
                res.add_error("orientation", f"Invalid orientation '{reqs.orientation}'")

        if reqs.entrance_facing is not None:
            if reqs.entrance_facing.lower() not in CARDINAL_DIRECTIONS:
                res.add_error("entrance_facing", f"Invalid entrance facing direction '{reqs.entrance_facing}'")

    def _validate_floors_and_rooms(self, reqs: Requirements, res: RequirementValidationResult) -> None:
        if reqs.target_floors is not None and reqs.target_floors <= 0:
            res.add_error("target_floors", f"Target floors must be positive integer, got {reqs.target_floors}")

        floor_numbers = [f.floor_number for f in reqs.floors]
        if floor_numbers:
            # Check sequential floor numbers starting from 1
            sorted_nums = sorted(floor_numbers)
            if sorted_nums[0] != 1:
                res.add_error("floors", f"Floor numbering must start at 1, starts at {sorted_nums[0]}")
            for expected, actual in enumerate(sorted_nums, start=1):
                if expected != actual:
                    res.add_error("floors", f"Floor numbers must be contiguous without gaps. Expected {expected}, got {actual}")

        # Check staircase requirement for multi-floor
        if (reqs.target_floors and reqs.target_floors > 1) or len(reqs.floors) > 1:
            for f in reqs.floors:
                if not f.staircase_required:
                    res.add_warning("staircase_required", f"Multi-floor building requires staircase on Floor {f.floor_number}")

        # Validate each floor's rooms
        for f in reqs.floors:
            self._validate_room_requirements(f, res)

    def _validate_room_requirements(self, floor: FloorRequirement, res: RequirementValidationResult) -> None:
        for r in floor.room_requirements:
            fn = floor.floor_number
            rt = r.room_type or "unspecified"

            # Room counts
            if r.min_count < 1:
                res.add_error("min_count", f"Room count must be at least 1 for {rt}", floor=fn, room=rt)
            if r.max_count is not None and r.max_count < r.min_count:
                res.add_error("max_count", f"max_count ({r.max_count}) cannot be less than min_count ({r.min_count}) for {rt}", floor=fn, room=rt)

            # Area bounds
            areas = [("min_area_sqm", r.min_area_sqm),
                     ("preferred_area_sqm", r.preferred_area_sqm),
                     ("max_area_sqm", r.max_area_sqm)]
            for name, val in areas:
                if val is not None and val <= 0:
                    res.add_error(name, f"{name} must be positive, got {val} for {rt}", floor=fn, room=rt)

            if r.min_area_sqm and r.max_area_sqm and r.min_area_sqm > r.max_area_sqm:
                res.add_error("area_range", f"min_area_sqm ({r.min_area_sqm}) exceeds max_area_sqm ({r.max_area_sqm}) for {rt}", floor=fn, room=rt)

            if r.preferred_area_sqm and r.min_area_sqm and r.preferred_area_sqm < r.min_area_sqm:
                res.add_error("preferred_area_sqm", f"preferred_area_sqm ({r.preferred_area_sqm}) is less than min_area_sqm ({r.min_area_sqm}) for {rt}", floor=fn, room=rt)

            if r.preferred_area_sqm and r.max_area_sqm and r.preferred_area_sqm > r.max_area_sqm:
                res.add_error("preferred_area_sqm", f"preferred_area_sqm ({r.preferred_area_sqm}) exceeds max_area_sqm ({r.max_area_sqm}) for {rt}", floor=fn, room=rt)

            # Relationship checks
            if rt in r.adjacency:
                res.add_error("adjacency", f"Room {rt} cannot have self-adjacency", floor=fn, room=rt)

            if rt in r.separation:
                res.add_error("separation", f"Room {rt} cannot have self-separation", floor=fn, room=rt)

            conflicts = set(r.adjacency).intersection(set(r.separation))
            if conflicts:
                res.add_error("relationships", f"Room {rt} has conflicting adjacency and separation with {list(conflicts)}", floor=fn, room=rt)

            if r.attached_to and r.attached_to == rt:
                res.add_error("attached_to", f"Room {rt} cannot be attached to itself", floor=fn, room=rt)
