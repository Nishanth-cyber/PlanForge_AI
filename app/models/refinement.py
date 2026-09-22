"""Refinement data contracts for validation-driven architectural correction.

The Refinement System represents CORRECT:
- Tracks structured modifications to architectural design proposals
- Records iterative validation-refinement progress for explainability and evaluation
- Preserves upstream immutability invariants: ASAA allocations, requirements, and floor assignments
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.validation import ValidationReport
from app.utils.ids import generate_id


class RefinementStatus(str, Enum):
    """Execution status of the refinement loop."""
    VALID_ON_INITIAL_PASS = "valid_on_initial_pass"
    VALID_AFTER_REFINEMENT = "valid_after_refinement"
    CONVERGED = "valid_after_refinement"  # Alias for valid_after_refinement
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    REFINEMENT_FAILED = "refinement_failed"
    REFINEMENT_OUTPUT_INVALID = "refinement_output_invalid"
    INFEASIBLE_UNDER_CONSTRAINTS = "infeasible_under_constraints"


@dataclass
class RefinementChange:
    """A granular, structured record of a single architectural design modification."""
    id: str = field(default_factory=generate_id)
    room_id: str = ""
    field_changed: str = ""  # e.g., "intended_dimensions", "intended_shape", "doors", "windows"
    old_value: Any = None
    new_value: Any = None
    reason: str = ""
    validation_issue_ids: list[str] = field(default_factory=list)
    floor_number: int = 1


@dataclass
class RefinementIterationRecord:
    """Snapshot of a single refinement iteration."""
    iteration: int = 0
    design_version: int = 0
    error_count: int = 0
    warning_count: int = 0
    score: float = 100.0
    issue_ids: list[str] = field(default_factory=list)
    changes: list[RefinementChange] = field(default_factory=list)
    validation_status: str = "pending"
    overall_valid: bool = False


@dataclass
class RefinementResult:
    """Complete authoritative outcome of the iterative refinement loop."""
    id: str = field(default_factory=generate_id)
    status: RefinementStatus = RefinementStatus.REFINEMENT_FAILED
    initial_design: Optional[ArchitecturalDesignSet] = None
    final_design: Optional[ArchitecturalDesignSet] = None
    final_floor_plan_set: Optional[FloorPlanSet] = None
    iterations: list[RefinementIterationRecord] = field(default_factory=list)
    validation_reports: list[ValidationReport] = field(default_factory=list)
    changes: list[RefinementChange] = field(default_factory=list)
    termination_reason: str = ""

    @property
    def total_iterations(self) -> int:
        """Total number of refinement iterations attempted."""
        return len(self.iterations)

    @property
    def final_report(self) -> Optional[ValidationReport]:
        """Most recent validation report."""
        return self.validation_reports[-1] if self.validation_reports else None

    @property
    def is_valid(self) -> bool:
        """Whether the final floor plan set is fully valid."""
        return self.status in {
            RefinementStatus.VALID_ON_INITIAL_PASS,
            RefinementStatus.VALID_AFTER_REFINEMENT,
        }

