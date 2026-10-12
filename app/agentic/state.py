"""Shared, structured project state for the observe-decide-act-evaluate loop.

``ProjectState`` is the single source of truth an agentic run reads and writes. Domain objects
(requirements, allocations, geometry, ...) live in ``artifacts`` (private, never serialized);
everything else is small and JSON-safe so it can be logged, traced and shown in the UI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.agentic.budget import Budget
from app.agentic.candidates import CandidateManager, CandidateRecord
from app.agentic.util import to_jsonable


class RunStatus(str, Enum):
    RUNNING = "running"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    INFEASIBLE = "infeasible"
    NEEDS_CLARIFICATION = "needs_clarification"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    RESUMABLE = "resumable"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STALLED = "stalled"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self is not RunStatus.RUNNING

    @property
    def is_paused(self) -> bool:
        return self in (
            RunStatus.WAITING_FOR_CLARIFICATION,
            RunStatus.NEEDS_CLARIFICATION,
            RunStatus.RESUMABLE,
        )

    @property
    def is_completed(self) -> bool:
        return self in (RunStatus.ACCEPTED, RunStatus.COMPLETED)


@dataclass
class Finding:
    """A normalized validation finding. ``hard`` findings are those with severity ``error``."""

    code: str
    severity: str = "error"
    message: str = ""
    target: Optional[str] = None
    floor: Optional[int] = None
    suggested_actions: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    id: str = ""

    @property
    def hard(self) -> bool:
        return self.severity == "error"

    @property
    def signature(self) -> str:
        """Identity that is stable across re-validations (ids are not)."""
        return f"{self.code}|{self.target}|{self.floor}|{self.severity}"

    @classmethod
    def from_any(cls, obj: Any) -> "Finding":
        if isinstance(obj, Finding):
            return obj
        if not isinstance(obj, dict):
            raise TypeError(f"Cannot build Finding from {type(obj).__name__}")
        return cls(
            code=str(obj.get("code") or obj.get("check") or obj.get("category") or "unknown"),
            severity=str(obj.get("severity", "error")),
            message=str(obj.get("message", "")),
            target=obj.get("target") or obj.get("room_id") or obj.get("target_id"),
            floor=obj.get("floor", obj.get("floor_number")),
            suggested_actions=list(obj.get("suggested_actions") or []),
            evidence=dict(obj.get("evidence") or obj.get("details") or {}),
            id=str(obj.get("id", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(
            {
                "id": self.id,
                "code": self.code,
                "severity": self.severity,
                "hard": self.hard,
                "message": self.message,
                "target": self.target,
                "floor": self.floor,
                "suggested_actions": self.suggested_actions,
                "evidence": self.evidence,
            }
        )


@dataclass
class DecisionRecord:
    """A decision recorded at the moment it is made (before the action runs)."""

    id: str
    step: int
    agent: str
    kind: str
    tool: Optional[str]
    args: Dict[str, Any]
    rationale: str
    source: str  # llm | rules | fallback | scripted
    fallback_reason: Optional[str] = None
    considered: List[str] = field(default_factory=list)
    state_fingerprint: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    status: str = "accepted"  # accepted | rejected
    rejection_reason: Optional[str] = None
    outcome: Optional[str] = None  # improved | informative | unchanged | worsened | error
    outcome_detail: str = ""
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self.__dict__)


@dataclass
class ToolCallRecord:
    id: str
    step: int
    decision_id: str
    tool: str
    args: Dict[str, Any]
    ok: bool
    outcome: str
    summary: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    attempt: int = 1
    artifacts_written: List[str] = field(default_factory=list)
    findings_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self.__dict__)


@dataclass
class ProjectState:
    project_id: str
    goal: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)

    # Private domain objects (never serialized or sent to a UI)
    artifacts: Dict[str, Any] = field(default_factory=dict, repr=False)
    artifact_versions: Dict[str, int] = field(default_factory=dict)
    state_version: int = 1

    # Small public facts
    facts: Dict[str, Any] = field(default_factory=dict)
    strategy: Dict[str, Any] = field(default_factory=dict)
    open_questions: List[str] = field(default_factory=list)

    # Validation evidence
    findings: List[Finding] = field(default_factory=list)
    has_findings: bool = False
    findings_scope: Tuple[str, ...] = ()
    findings_stamp: Dict[str, int] = field(default_factory=dict)
    findings_seq: int = 0
    findings_history: List[Dict[str, Any]] = field(default_factory=list)
    infeasibility_evidence: List[Dict[str, Any]] = field(default_factory=list)

    # Execution record
    decisions: List[DecisionRecord] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    executed: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_rejection: Optional[str] = None
    step: int = 0
    stalled: bool = False
    no_progress_streak: int = 0

    # Completion & Paused Workflow Status
    status: RunStatus = RunStatus.RUNNING
    status_reason: str = ""
    acceptance_evidence: Dict[str, Any] = field(default_factory=dict)

    # Phase 7: Interactive clarification & resumable state tracking
    pending_clarification: Optional[Any] = None
    clarification_history: List[Any] = field(default_factory=list)
    clarification_responses: List[Any] = field(default_factory=list)
    requirement_changes: List[Any] = field(default_factory=list)
    paused_stage: Optional[str] = None
    invalidated_artifacts: Set[str] = field(default_factory=set)

    budget: Budget = field(default_factory=Budget)
    candidate_manager: CandidateManager = field(default_factory=CandidateManager, repr=False)

    # ------------------------------------------------------------------ candidate management
    def record_candidate(self, source_action: str) -> Tuple[Optional[CandidateRecord], bool]:
        """Record and evaluate the current design as a candidate."""
        fp = self.get_artifact("floor_plan_set")
        if not fp:
            return None, False
        val_rep = getattr(fp, "validation_report", None)
        rec, is_new_best = self.candidate_manager.register_candidate(
            step=self.step,
            source_action=source_action,
            floor_plan_set=fp,
            validation_report=val_rep,
            architectural_design_set=self.get_artifact("architectural_design_set"),
            allocation_set=self.get_artifact("allocation_set"),
            planning_spec=self.get_artifact("planning_spec"),
            requirements=self.get_artifact("requirements"),
        )
        return rec, is_new_best

    def restore_best_valid(self) -> bool:
        """Revert active artifacts to the best known valid candidate."""
        best = self.candidate_manager.get_best_valid()
        if not best:
            return False
        if best.floor_plan_set:
            self.set_artifact("floor_plan_set", best.floor_plan_set)
        if best.architectural_design_set:
            self.set_artifact("architectural_design_set", best.architectural_design_set)
        if best.allocation_set:
            self.set_artifact("allocation_set", best.allocation_set)
        if best.planning_spec:
            self.set_artifact("planning_spec", best.planning_spec)
        return True

    # ------------------------------------------------------------------ artifacts
    def has_artifact(self, key: str) -> bool:
        return key in self.artifacts

    def get_artifact(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value
        self.artifact_versions[key] = self.artifact_versions.get(key, 0) + 1
        self.state_version += 1

    def version_of(self, keys: Iterable[str]) -> Dict[str, int]:
        return {k: self.artifact_versions.get(k, 0) for k in keys}

    @property
    def version(self) -> int:
        return self.state_version

    @version.setter
    def version(self, val: int) -> None:
        self.state_version = val

    @property
    def is_paused(self) -> bool:
        return self.status.is_paused

    @property
    def is_completed(self) -> bool:
        return self.status.is_completed

    def increment_version(self) -> int:
        self.state_version += 1
        return self.state_version

    def invalidate_downstream(self, stage: str = "requirements") -> Set[str]:
        """Atomically invalidate downstream artifacts when upstream requirements change."""
        invalidated = set()
        downstream_map = {
            "requirements": ["planning_spec", "allocation_set", "architectural_design_set", "floor_plan_set", "alternative_set"],
            "feasibility": ["planning_spec", "allocation_set", "architectural_design_set", "floor_plan_set", "alternative_set"],
            "feasibility_check": ["planning_spec", "allocation_set", "architectural_design_set", "floor_plan_set", "alternative_set"],
            "planning": ["allocation_set", "architectural_design_set", "floor_plan_set", "alternative_set"],
            "allocation": ["architectural_design_set", "floor_plan_set", "alternative_set"],
        }
        to_clear = downstream_map.get(stage, ["planning_spec", "allocation_set", "architectural_design_set", "floor_plan_set", "alternative_set"])
        for k in to_clear:
            if k in self.artifacts:
                del self.artifacts[k]
            invalidated.add(k)
        self.facts.pop("feasible", None)
        self.facts.pop("feasibility_checked", None)
        self.facts.pop("deficits", None)
        self.facts.pop("export_bundle_path", None)
        self.invalidated_artifacts.update(invalidated)
        return invalidated

    # ------------------------------------------------------------------ findings
    def apply_findings(self, findings: Iterable[Any], scope_keys: Iterable[str]) -> None:
        """Record a *fresh* validation of ``scope_keys`` at their current versions."""
        scope = tuple(scope_keys)
        self.findings = [Finding.from_any(f) for f in findings]
        self.has_findings = True
        self.findings_scope = scope
        self.findings_stamp = self.version_of(scope)
        self.findings_seq += 1
        self.findings_history.append(
            {
                "seq": self.findings_seq,
                "step": self.step,
                "hard": len(self.hard_findings()),
                "warnings": len(self.warning_findings()),
                "signatures": sorted(f.signature for f in self.findings),
            }
        )

    def hard_findings(self) -> List[Finding]:
        return [f for f in self.findings if f.hard]

    def warning_findings(self) -> List[Finding]:
        return [f for f in self.findings if not f.hard]

    def validation_is_current(self) -> bool:
        """True only if findings exist and the validated artifacts have not changed since."""
        return self.has_findings and self.findings_stamp == self.version_of(self.findings_scope)

    # ------------------------------------------------------------------ fingerprint
    def fingerprint(self) -> str:
        payload = {
            "versions": self.artifact_versions,
            "facts": to_jsonable(self.facts),
            "strategy": to_jsonable(self.strategy),
            "questions": list(self.open_questions),
            "findings": sorted(f.signature for f in self.findings),
            "has_findings": self.has_findings,
            "stamp": self.findings_stamp,
            "infeasible": len(self.infeasibility_evidence),
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------ records
    def record_decision(self, **kwargs: Any) -> DecisionRecord:
        rec = DecisionRecord(id=f"d{len(self.decisions) + 1}", step=self.step, **kwargs)
        self.decisions.append(rec)
        return rec

    def record_tool_call(self, **kwargs: Any) -> ToolCallRecord:
        rec = ToolCallRecord(id=f"t{len(self.tool_calls) + 1}", step=self.step, **kwargs)
        self.tool_calls.append(rec)
        return rec

    def tool_call_count(self, tool: str) -> int:
        return sum(1 for t in self.tool_calls if t.tool == tool)

    # ------------------------------------------------------------------ repeat blocking view
    def blocked_keys(self) -> Set[str]:
        fp = self.fingerprint()
        return {e["action_key"] for e in self.executed.values() if e["fingerprint"] == fp and e["blocked"]}

    def blocked_actions(self) -> List[Dict[str, Any]]:
        fp = self.fingerprint()
        return [
            {"tool": e["tool"], "args": e["args"], "attempts": e["attempts"]}
            for e in self.executed.values()
            if e["fingerprint"] == fp and e["blocked"]
        ]

    # ------------------------------------------------------------------ views
    def public_summary(self, max_findings: int = 10, recent_decisions: int = 5) -> Dict[str, Any]:
        """Compact observation handed to policies (LLM or rules). Contains no artifacts or secrets."""
        hard = self.hard_findings()
        top = sorted(self.findings, key=lambda f: (not f.hard, f.code))[:max_findings]
        return to_jsonable(
            {
                "goal": self.goal,
                "status": self.status.value,
                "step": self.step,
                "budget_remaining": self.budget.remaining(),
                "inputs": self.inputs,
                "artifacts_present": self.version_of(sorted(self.artifacts)),
                "facts": self.facts,
                "strategy": self.strategy,
                "open_questions": self.open_questions,
                "validation": {
                    "validated": self.has_findings,
                    "current": self.validation_is_current(),
                    "scope": list(self.findings_scope),
                    "hard_errors": len(hard),
                    "warnings": len(self.warning_findings()),
                    "top_findings": [f.to_dict() for f in top],
                },
                "infeasibility_evidence": self.infeasibility_evidence[-3:],
                "blocked_actions": self.blocked_actions(),
                "stalled": self.stalled,
                "no_progress_streak": self.no_progress_streak,
                "last_rejection": self.last_rejection,
                "recent_decisions": [
                    {
                        "step": d.step,
                        "tool": d.tool or d.kind,
                        "status": d.status,
                        "outcome": d.outcome,
                        "source": d.source,
                    }
                    for d in self.decisions[-recent_decisions:]
                ],
            }
        )

    def to_public_dict(self, max_items: int = 200) -> Dict[str, Any]:
        """UI/API-safe view: execution record and status only. No artifacts, prompts or raw LLM output."""
        return to_jsonable(
            {
                "project_id": self.project_id,
                "status": self.status.value,
                "status_reason": self.status_reason,
                "step": self.step,
                "budget": self.budget.to_dict(),
                "facts": self.facts,
                "strategy": self.strategy,
                "open_questions": self.open_questions,
                "validation": self.public_summary()["validation"],
                "infeasibility_evidence": self.infeasibility_evidence,
                "acceptance_evidence": self.acceptance_evidence,
                "decisions": [d.to_dict() for d in self.decisions[-max_items:]],
                "tool_calls": [t.to_dict() for t in self.tool_calls[-max_items:]],
                "findings_history": self.findings_history[-max_items:],
                "candidate_history": self.candidate_manager.all_summaries()[:max_items],
                "best_candidate": self.candidate_manager.get_best_overall().to_dict() if self.candidate_manager.get_best_overall() else None,
                "pending_clarification": self.pending_clarification.to_dict() if hasattr(self.pending_clarification, "to_dict") else self.pending_clarification,
                "clarification_history": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.clarification_history],
                "requirement_changes": [rc.to_dict() if hasattr(rc, "to_dict") else rc for rc in self.requirement_changes],
                "paused_stage": self.paused_stage,
                "is_paused": self.status.is_paused,
                "state_version": self.state_version,
            },
            max_items=max_items,
        )
