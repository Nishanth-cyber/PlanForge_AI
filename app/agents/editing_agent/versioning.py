"""Project Design Versioning and Undo Manager for PlanForge AI.

Maintains complete historical records for each accepted architectural design edit:
- Project ID and design version IDs (v1, v2, ...).
- User's original editing instruction.
- Structured edit operations applied.
- Affected room and element IDs.
- Complete domain snapshots: ArchitecturalDesignSet, AllocationSet, FloorPlanSet, ValidationReport.
- Summary of changes and timestamps.
- Safe undo to restore previous design versions without creating duplicate projects.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.validation import ValidationReport

logger = logging.getLogger(__name__)


@dataclass
class DesignVersion:
    """Snapshot of a single design version."""

    version_id: str
    project_id: str
    parent_version_id: Optional[str] = None
    user_instruction: str = ""
    operations: List[Dict[str, Any]] = field(default_factory=list)
    affected_room_ids: List[str] = field(default_factory=list)
    affected_element_ids: List[str] = field(default_factory=list)
    architectural_design_set: Optional[ArchitecturalDesignSet] = None
    allocation_set: Optional[AllocationSet] = None
    floor_plan_set: Optional[FloorPlanSet] = None
    validation_report: Optional[ValidationReport] = None
    summary_of_changes: str = ""
    timestamp: float = field(default_factory=time.time)
    export_artifacts: List[str] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Summary representation for API and frontend history list."""
        val_score = 100.0
        val_valid = True
        total_errors = 0
        total_warnings = 0
        if self.validation_report:
            val_score = round(float(self.validation_report.overall_score), 1)
            val_valid = bool(self.validation_report.overall_valid)
            total_errors = self.validation_report.total_errors
            total_warnings = self.validation_report.total_warnings

        return {
            "version_id": self.version_id,
            "project_id": self.project_id,
            "parent_version_id": self.parent_version_id,
            "instruction": self.user_instruction,
            "summary": self.summary_of_changes,
            "timestamp": self.timestamp,
            "affected_room_ids": list(self.affected_room_ids),
            "affected_element_ids": list(self.affected_element_ids),
            "is_valid": val_valid,
            "validation_score": val_score,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
        }


class ProjectVersionHistory:
    """Thread-safe version history manager for an architectural project."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.versions: List[DesignVersion] = []
        self.active_version_id: Optional[str] = None

    def initialize_base(
        self,
        architectural_design_set: ArchitecturalDesignSet,
        allocation_set: AllocationSet,
        floor_plan_set: FloorPlanSet,
        validation_report: Optional[ValidationReport] = None,
        project_name: str = "",
    ) -> DesignVersion:
        """Record the initial generated design as version 1 (baseline)."""
        if self.versions:
            return self.versions[0]

        v1 = DesignVersion(
            version_id="v1",
            project_id=self.project_id,
            parent_version_id=None,
            user_instruction="Initial Generation",
            operations=[],
            affected_room_ids=[],
            affected_element_ids=[],
            architectural_design_set=copy.deepcopy(architectural_design_set),
            allocation_set=copy.deepcopy(allocation_set),
            floor_plan_set=copy.deepcopy(floor_plan_set),
            validation_report=copy.deepcopy(validation_report) if validation_report else None,
            summary_of_changes="Initial generation baseline.",
            timestamp=time.time(),
        )
        self.versions.append(v1)
        self.active_version_id = "v1"
        return v1

    def record_version(
        self,
        user_instruction: str,
        operations: List[Dict[str, Any]],
        affected_room_ids: List[str],
        affected_element_ids: List[str],
        architectural_design_set: ArchitecturalDesignSet,
        allocation_set: AllocationSet,
        floor_plan_set: FloorPlanSet,
        validation_report: Optional[ValidationReport],
        summary_of_changes: str,
    ) -> DesignVersion:
        """Create and append a new design version."""
        parent_id = self.active_version_id or ("v1" if self.versions else None)
        next_num = len(self.versions) + 1
        new_version_id = f"v{next_num}"

        version = DesignVersion(
            version_id=new_version_id,
            project_id=self.project_id,
            parent_version_id=parent_id,
            user_instruction=user_instruction,
            operations=operations,
            affected_room_ids=affected_room_ids,
            affected_element_ids=affected_element_ids,
            architectural_design_set=copy.deepcopy(architectural_design_set),
            allocation_set=copy.deepcopy(allocation_set),
            floor_plan_set=copy.deepcopy(floor_plan_set),
            validation_report=copy.deepcopy(validation_report) if validation_report else None,
            summary_of_changes=summary_of_changes,
            timestamp=time.time(),
        )

        self.versions.append(version)
        self.active_version_id = new_version_id
        return version

    @property
    def can_undo(self) -> bool:
        """True if there is a previous version to restore."""
        if not self.versions or len(self.versions) <= 1:
            return False
        curr_idx = self._current_index()
        return curr_idx > 0

    def undo(self) -> Optional[DesignVersion]:
        """Restore the immediate previous version safely."""
        if not self.can_undo:
            return None

        curr_idx = self._current_index()
        prev_version = self.versions[curr_idx - 1]
        self.active_version_id = prev_version.version_id
        return prev_version

    def get_active_version(self) -> Optional[DesignVersion]:
        """Retrieve the currently active DesignVersion snapshot."""
        if not self.versions:
            return None
        if not self.active_version_id:
            return self.versions[-1]
        for v in self.versions:
            if v.version_id == self.active_version_id:
                return v
        return self.versions[-1]

    def _current_index(self) -> int:
        """Find list index of active version."""
        if not self.active_version_id or not self.versions:
            return len(self.versions) - 1
        for i, v in enumerate(self.versions):
            if v.version_id == self.active_version_id:
                return i
        return len(self.versions) - 1

    def list_summaries(self) -> List[Dict[str, Any]]:
        """List summary descriptions of all recorded versions."""
        return [v.to_summary_dict() for v in self.versions]
