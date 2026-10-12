"""Hybrid Hierarchical Multi-Agent Coordination for PlanForge.

Defines typed communication schemas, constraint evidence structures,
the evidence-based ConflictResolver, and specialized agent coordinators.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agentic.budget import Budget
from app.agentic.candidates import CandidateEvaluation, CandidateManager, CandidateRecord
from app.agentic.events import InMemoryEventLog
from app.agentic.state import Finding, ProjectState, RunStatus
from app.agentic.util import to_jsonable
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Structured Coordination Schemas
# ============================================================================

class ConstraintPriority(enum.IntEnum):
    """5-tier priority hierarchy for evidence-based conflict resolution.

    Lower value indicates higher priority (Level 1 is supreme authority).
    """
    MANDATORY_USER = 1        # Explicit user requirements & hard statutory minimums
    PHYSICAL_FEASIBILITY = 2  # Physical site boundaries & geometric non-overlap
    VALIDATOR_FINDING = 3     # Independent FloorPlanValidator verdicts (authoritative)
    PLANNING_INTENT = 4       # Approved spatial relationships & zoning hierarchy
    SOFT_PREFERENCE = 5       # User styling preferences, aspect ratios, soft warnings


@dataclass
class ConstraintEvidence:
    """Structured evidence item supporting or challenging an agent proposal."""

    constraint_id: str
    category: str  # "mandatory_user", "physical_feasibility", "validator_finding", "planning_intent", "soft_preference"
    priority: int = ConstraintPriority.MANDATORY_USER
    description: str = ""
    is_hard: bool = True
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    source: str = ""  # e.g., "requirements", "shapely_geometry", "validator", "asaa"

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class AgentTask:
    """A formal task delegated to a specialized agent by the Hierarchical Orchestrator."""

    task_id: str
    target_agent: str
    task_type: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    state_version: int = 1
    input_artifacts: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def assigned_agent(self) -> str:
        return self.target_agent

    @property
    def intent(self) -> str:
        return self.task_type

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class AgentProposal:
    """A structured action proposal submitted by an agent for orchestrator review."""

    proposal_id: str
    task_id: str
    agent_id: str
    state_version: int
    proposed_action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    supporting_evidence: List[ConstraintEvidence] = field(default_factory=list)
    expected_benefit: str = ""
    affected_components: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    confidence: float = 1.0
    requires_review_by: Optional[str] = None
    status: str = "proposed"  # "proposed", "accepted", "rejected", "superseded"
    rejection_reason: Optional[str] = None
    evidence: Optional[List[ConstraintEvidence]] = None

    def __post_init__(self) -> None:
        if self.evidence and not self.supporting_evidence:
            self.supporting_evidence = self.evidence
        elif self.supporting_evidence and not self.evidence:
            self.evidence = self.supporting_evidence

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class AgentResult:
    """The verifiable outcome produced by executing an approved agent action."""

    result_id: str
    task_id: str
    agent_id: str
    ok: bool
    outcome: str  # "ok", "error", "infeasible", "needs_input", "no_effect"
    summary: str
    artifacts_produced: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    execution_ms: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class AgentMessage:
    """A direct typed message exchanged between specialized agents."""

    message_id: str
    sender: str
    recipient: str
    message_type: str  # "task_assignment", "proposal_submitted", "conflict_raised", "clarification_needed"
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class ConflictRecord:
    """Documentation of a detected disagreement between agent proposals and its resolution."""

    conflict_id: str
    task_id: str
    disagreeing_agents: List[str]
    proposals: List[AgentProposal]
    disputed_constraints: List[str]
    resolution_strategy: str
    accepted_proposal_id: Optional[str] = None
    rejection_reasons: Dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    evidence: List[str] = field(default_factory=list)

    @property
    def winner_id(self) -> Optional[str]:
        return self.accepted_proposal_id

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class CoordinationDecision:
    """A recorded decision made by the Hierarchical Orchestrator."""

    decision_id: str
    cycle: int
    selected_agent: str
    assigned_task: AgentTask
    rationale: str
    conflict_resolved: Optional[ConflictRecord] = None
    evidence: List[str] = field(default_factory=list)
    source: str = "llm"  # "llm", "rules", "fallback"

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


from app.agentic.clarification import (
    AlternativeFeasibilityType,
    ClarificationCategory,
    ClarificationDecisionPolicy,
    ClarificationOption,
    ClarificationRequest,
    ClarificationResponse,
    ClarificationResponseValidator,
    ClarificationStatus,
    RequirementChangeRecord,
)


@dataclass
class WorkflowTermination:
    """Definitive terminal outcome of a multi-agent workflow run."""

    status: RunStatus
    reason: str
    is_success: bool
    candidate_id: Optional[str] = None
    infeasibility_report: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


# ============================================================================
# 2. Evidence-Based Conflict Resolver
# ============================================================================

class ConflictResolver:
    """Authoritative arbiter resolving disagreements between specialized agent proposals.

    Enforces the strict 5-tier priority hierarchy:
    1. Explicit user requirements and mandatory constraints (Level 1)
    2. Physical feasibility and deterministic geometry (Level 2)
    3. Independent validator findings (Level 3)
    4. Approved spatial planning intent (Level 4)
    5. Soft preferences and design-quality objectives (Level 5)

    Disqualifies any proposal that violates a higher-level constraint.
    Never relies on ungrounded confidence scores or majority voting.
    """

    @classmethod
    def resolve(
        cls,
        task_id: str,
        proposals: List[AgentProposal],
        state: ProjectState,
    ) -> Tuple[Optional[AgentProposal], ConflictRecord]:
        """Resolve a conflict between multiple competing proposals based on evidence.

        Returns:
            Tuple of (accepted_proposal, conflict_record)
        """
        cid = f"conflict_{generate_id()}"
        agents = [p.agent_id for p in proposals]
        rejection_reasons: Dict[str, str] = {}
        disputed: List[str] = []

        valid_candidates: List[Tuple[AgentProposal, int, float]] = []

        for p in proposals:
            # Check 1: Mandatory user requirements & hard constraints (Level 1)
            violates_user_req = False
            for evid in p.supporting_evidence:
                if evid.priority == ConstraintPriority.MANDATORY_USER:
                    if not evid.is_hard:
                        disputed.append(evid.constraint_id)
                    elif any(term in evid.description.lower() for term in ("omit", "violat", "breach", "remove", "disregard", "below minimum")):
                        violates_user_req = True
                        rejection_reasons[p.proposal_id] = (
                            f"Violates hard constraint: {evid.description}"
                        )
            # Check for explicit illegal parameter (e.g. attempting to remove mandatory room)
            if p.parameters.get("relax_mandatory_rooms") or p.parameters.get("reduce_rooms"):
                violates_user_req = True
                rejection_reasons[p.proposal_id] = (
                    "Violates Level 1 Priority: Cannot silently relax or omit mandatory room requirements."
                )
            if p.parameters.get("target_area_sqm", 0.0) < 0:
                violates_user_req = True
                rejection_reasons[p.proposal_id] = (
                    "Violates Level 1 Priority: Negative target area specified."
                )

            if violates_user_req:
                p.status = "rejected"
                p.rejection_reason = rejection_reasons[p.proposal_id]
                continue

            # Check 2: Physical feasibility & site boundary (Level 2)
            violates_feasibility = False
            for evid in p.supporting_evidence:
                if evid.priority == ConstraintPriority.PHYSICAL_FEASIBILITY:
                    if evid.metric_value is not None and evid.threshold is not None:
                        if evid.metric_value > evid.threshold:
                            violates_feasibility = True
                            rejection_reasons[p.proposal_id] = (
                                f"Violates Level 2 Priority: Physical feasibility exceeded ({evid.metric_value} > {evid.threshold})."
                            )
            if violates_feasibility:
                p.status = "rejected"
                p.rejection_reason = rejection_reasons[p.proposal_id]
                continue

            # Check 3: Validator authority (Level 3)
            # A proposal cannot claim a hard error is ignored
            if p.parameters.get("ignore_hard_errors"):
                p.status = "rejected"
                p.rejection_reason = "Violates Level 3 Priority: FloorPlanValidator authority cannot be bypassed."
                rejection_reasons[p.proposal_id] = p.rejection_reason
                continue

            # Compute effective priority score
            # Highest priority among supporting evidence
            min_priority_level = min(
                (ev.priority for ev in p.supporting_evidence),
                default=ConstraintPriority.SOFT_PREFERENCE,
            )
            valid_candidates.append((p, int(min_priority_level), p.confidence))

        if not valid_candidates:
            record = ConflictRecord(
                conflict_id=cid,
                task_id=task_id,
                disagreeing_agents=agents,
                proposals=proposals,
                disputed_constraints=disputed,
                resolution_strategy="all_rejected_mandatory_violation",
                accepted_proposal_id=None,
                rejection_reasons=rejection_reasons,
                rationale="All proposals rejected due to mandatory constraint or physical feasibility violations.",
                evidence=["mandatory_constraint_protection"],
            )
            return None, record

        # Sort valid candidates:
        # 1. Lower priority level integer = higher authority (Level 1 > Level 2 > ...)
        # 2. Higher confidence
        # 3. Deterministic tie-breaking on proposal_id
        valid_candidates.sort(key=lambda item: (item[1], -item[2], item[0].proposal_id))
        winning_proposal, winning_level, win_conf = valid_candidates[0]

        winning_proposal.status = "accepted"

        # Mark superseded
        for p, _, _ in valid_candidates[1:]:
            p.status = "superseded"
            rejection_reasons[p.proposal_id] = (
                f"Superseded by {winning_proposal.agent_id} (Level {winning_level} authority, confidence {win_conf:.2f})"
            )
            p.rejection_reason = rejection_reasons[p.proposal_id]

        record = ConflictRecord(
            conflict_id=cid,
            task_id=task_id,
            disagreeing_agents=agents,
            proposals=proposals,
            disputed_constraints=disputed,
            resolution_strategy=f"priority_hierarchy_level_{winning_level}",
            accepted_proposal_id=winning_proposal.proposal_id,
            rejection_reasons=rejection_reasons,
            rationale=(
                f"Accepted proposal {winning_proposal.proposal_id} from {winning_proposal.agent_id} "
                f"under Priority Level {winning_level} ({winning_proposal.expected_benefit})."
            ),
            evidence=[e.description for e in winning_proposal.supporting_evidence[:3]],
        )
        return winning_proposal, record
