"""Structured Edit Operations for PlanForge AI.

Represents architectural modifications as validated, machine-readable operations
rather than asking the LLM to generate arbitrary coordinate geometry.

Supported operations:
- MODIFY_ROOM_DIMENSIONS: Change target area, width, or length of a room.
- MODIFY_ROOM_SHAPE: Change intended shape (rectangular, l_shaped, square).
- MODIFY_ROOM_POSITION: Move room closer to another space or alter orientation.
- MODIFY_ROOM_RELATIONSHIP: Update adjacency / separation constraints.
- ADD_ROOM: Add an architectural room programmatically.
- REMOVE_ROOM: Remove an existing room when permitted.
- ADD_DOOR: Propose a new door connecting functional spaces.
- MODIFY_DOOR: Update door width, height, type, or connected room.
- REMOVE_DOOR: Remove an existing door intent.
- ADD_WINDOW: Propose a new window on an exterior wall orientation.
- MODIFY_WINDOW: Update window width, height, or sill.
- REMOVE_WINDOW: Remove an existing window intent.
- MODIFY_ENTRANCE: Reposition the main entrance door orientation.
- MODIFY_CIRCULATION: Enhance corridor and circulation network.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EditOperationType(str, Enum):
    """Supported structured architectural edit operations."""

    MODIFY_ROOM_DIMENSIONS = "MODIFY_ROOM_DIMENSIONS"
    MODIFY_ROOM_SHAPE = "MODIFY_ROOM_SHAPE"
    MODIFY_ROOM_POSITION = "MODIFY_ROOM_POSITION"
    MODIFY_ROOM_RELATIONSHIP = "MODIFY_ROOM_RELATIONSHIP"
    ADD_ROOM = "ADD_ROOM"
    REMOVE_ROOM = "REMOVE_ROOM"
    ADD_DOOR = "ADD_DOOR"
    MODIFY_DOOR = "MODIFY_DOOR"
    REMOVE_DOOR = "REMOVE_DOOR"
    ADD_WINDOW = "ADD_WINDOW"
    MODIFY_WINDOW = "MODIFY_WINDOW"
    REMOVE_WINDOW = "REMOVE_WINDOW"
    MODIFY_ENTRANCE = "MODIFY_ENTRANCE"
    MODIFY_CIRCULATION = "MODIFY_CIRCULATION"


@dataclass
class EditOperation:
    """A validated, machine-readable modification operation."""

    operation: EditOperationType
    project_id: str = ""
    target_room_id: Optional[str] = None
    target_room_type: Optional[str] = None
    target_element_id: Optional[str] = None
    floor_number: int = 1
    changes: Dict[str, Any] = field(default_factory=dict)
    preserve_unaffected_rooms: bool = True
    preserve_floor_assignments: bool = True
    requires_validation: bool = True

    def validate(self) -> None:
        """Validate operation against schema and architectural invariants."""
        if not isinstance(self.operation, EditOperationType):
            try:
                self.operation = EditOperationType(str(self.operation))
            except ValueError as e:
                raise ValueError(f"Unsupported edit operation: {self.operation}") from e

        # Validate target specifications for element-level operations
        op = self.operation
        if op in (
            EditOperationType.MODIFY_ROOM_DIMENSIONS,
            EditOperationType.MODIFY_ROOM_SHAPE,
            EditOperationType.MODIFY_ROOM_POSITION,
        ):
            if not self.target_room_id and not self.target_room_type:
                raise ValueError(f"Operation {op} requires target_room_id or target_room_type")

        if op == EditOperationType.MODIFY_ROOM_DIMENSIONS:
            target_area = self.changes.get("target_area_sqm")
            dims = self.changes.get("intended_dimensions")
            scale = self.changes.get("scale_factor")
            if target_area is None and dims is None and scale is None:
                raise ValueError("MODIFY_ROOM_DIMENSIONS requires target_area_sqm, intended_dimensions, or scale_factor")
            if target_area is not None and target_area <= 0:
                raise ValueError(f"target_area_sqm must be positive, got {target_area}")

        if op == EditOperationType.MODIFY_ROOM_SHAPE:
            shape = self.changes.get("intended_shape")
            if shape not in ("rectangular", "l_shaped", "square", "custom"):
                raise ValueError(f"Unsupported room shape: {shape}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert operation to clean JSON dictionary."""
        d = asdict(self)
        d["operation"] = self.operation.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EditOperation:
        """Construct validated EditOperation from dictionary."""
        op_val = data.get("operation")
        op_type = EditOperationType(op_val) if isinstance(op_val, str) else op_val
        return cls(
            operation=op_type,
            project_id=data.get("project_id", ""),
            target_room_id=data.get("target_room_id"),
            target_room_type=data.get("target_room_type"),
            target_element_id=data.get("target_element_id"),
            floor_number=int(data.get("floor_number", 1)),
            changes=data.get("changes", {}),
            preserve_unaffected_rooms=data.get("preserve_unaffected_rooms", True),
            preserve_floor_assignments=data.get("preserve_floor_assignments", True),
            requires_validation=data.get("requires_validation", True),
        )


@dataclass
class EditPlan:
    """Execution plan containing one or more validated operations."""

    instruction: str
    operations: List[EditOperation] = field(default_factory=list)
    rationale: str = ""
    clarification_question: Optional[str] = None
    affected_rooms: List[str] = field(default_factory=list)
    affected_elements: List[str] = field(default_factory=list)
    intent: Optional[Any] = None

