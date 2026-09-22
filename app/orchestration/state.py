"""Pipeline state and stage lifecycle tracking data structures."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.agents.requirement_agent.completeness_gate import CompletenessResult
from app.explainability.models import DecisionTrace
from app.export.integrity import ExportIntegrityReport
from app.models.allocation import AllocationSet
from app.models.alternatives import DesignAlternativeSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.planning import PlanningSpec
from app.models.refinement import RefinementResult
from app.models.requirements import Requirements
from app.models.validation import ValidationReport


class StageName(str, Enum):
    """The 10 canonical pipeline stages of the PlanForge generative architecture."""
    REQUIREMENT = "REQUIREMENT"
    PLANNING = "PLANNING"
    ASAA = "ASAA"
    ARCHITECTURAL_DESIGN = "ARCHITECTURAL_DESIGN"
    GEOMETRY = "GEOMETRY"
    VALIDATION = "VALIDATION"
    REFINEMENT = "REFINEMENT"
    MULTI_DESIGN = "MULTI_DESIGN"
    EXPLAINABILITY = "EXPLAINABILITY"
    EXPORT = "EXPORT"


class StageStatus(str, Enum):
    """Controlled lifecycle states for an orchestration pipeline stage."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PARTIAL = "PARTIAL"


@dataclass
class StageRecord:
    """Detailed record of a stage's execution lifecycle."""
    stage_name: StageName
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert stage record to dictionary."""
        return {
            "stage_name": self.stage_name.value if isinstance(self.stage_name, Enum) else str(self.stage_name),
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 2),
            "error_message": self.error_message,
            "metadata": dict(self.metadata),
        }


@dataclass
class PipelineState:
    """State accumulator for an executing PlanForge pipeline run.

    Stores references to existing domain models produced by each stage
    without duplicating or mutating them.
    """
    project_id: str
    project_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Stage outputs (populated sequentially)
    raw_brief: Optional[str] = None
    requirements: Optional[Requirements] = None
    completeness_result: Optional[CompletenessResult] = None
    planning_spec: Optional[PlanningSpec] = None
    allocation_set: Optional[AllocationSet] = None
    architectural_design_set: Optional[ArchitecturalDesignSet] = None
    floor_plan_set: Optional[FloorPlanSet] = None
    validation_report: Optional[ValidationReport] = None
    refinement_result: Optional[RefinementResult] = None
    alternative_set: Optional[DesignAlternativeSet] = None
    decision_trace: Optional[DecisionTrace] = None
    export_bundle_path: Optional[str] = None
    export_integrity_report: Optional[ExportIntegrityReport] = None

    # Lifecycle tracking
    stage_records: Dict[StageName, StageRecord] = field(default_factory=dict)
    _stage_start_times: Dict[StageName, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.stage_records:
            for s in StageName:
                self.stage_records[s] = StageRecord(stage_name=s, status=StageStatus.PENDING)

    def start_stage(self, stage: StageName) -> None:
        """Mark a stage as currently running."""
        now_ts = datetime.now().isoformat()
        self._stage_start_times[stage] = time.perf_counter()
        rec = self.stage_records[stage]
        rec.status = StageStatus.RUNNING
        rec.started_at = now_ts

    def complete_stage(self, stage: StageName, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Mark a stage as successfully completed."""
        rec = self.stage_records[stage]
        rec.status = StageStatus.COMPLETED
        rec.completed_at = datetime.now().isoformat()
        start_t = self._stage_start_times.get(stage)
        if start_t is not None:
            rec.duration_ms = (time.perf_counter() - start_t) * 1000.0
        if metadata:
            rec.metadata.update(metadata)

    def fail_stage(self, stage: StageName, error_message: str) -> None:
        """Mark a stage as failed."""
        rec = self.stage_records[stage]
        rec.status = StageStatus.FAILED
        rec.completed_at = datetime.now().isoformat()
        rec.error_message = error_message
        start_t = self._stage_start_times.get(stage)
        if start_t is not None:
            rec.duration_ms = (time.perf_counter() - start_t) * 1000.0

    def skip_stage(self, stage: StageName, reason: str = "Skipped due to upstream failure or configuration") -> None:
        """Mark a stage as skipped."""
        rec = self.stage_records[stage]
        rec.status = StageStatus.SKIPPED
        rec.error_message = reason

    def skip_downstream_stages(self, from_stage: StageName, reason: str = "Skipped due to upstream failure") -> None:
        """Skip all stages following a given failed stage."""
        stages_list = list(StageName)
        try:
            idx = stages_list.index(from_stage)
            for s in stages_list[idx + 1:]:
                if self.stage_records[s].status == StageStatus.PENDING:
                    self.skip_stage(s, reason=reason)
        except ValueError:
            pass

    def get_stage_statuses(self) -> Dict[str, str]:
        """Return a mapping of stage names to status strings."""
        return {s.value: r.status.value for s, r in self.stage_records.items()}
