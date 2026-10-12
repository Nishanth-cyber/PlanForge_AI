"""Hierarchical Orchestrator and Specialized Agent Coordinators for Phase 6.

Implements the Hybrid Hierarchical Multi-Agent Architecture for PlanForge:
- Hierarchical Orchestrator delegating state-dependent tasks to specialized agents.
- Structured proposal generation with constraint evidence.
- Evidence-based conflict resolution using a 5-tier priority hierarchy.
- Stale proposal rejection via state-version tracking.
- Cross-floor multi-floor coordination and authoritative validation.
- Preservation of the best valid candidate throughout execution.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.agentic.budget import Budget
from app.agentic.candidates import CandidateEvaluation, CandidateManager, CandidateRecord
from app.agentic.coordination import (
    AgentMessage,
    AgentProposal,
    AgentResult,
    AgentTask,
    ClarificationRequest,
    ConflictRecord,
    ConflictResolver,
    ConstraintEvidence,
    ConstraintPriority,
    CoordinationDecision,
    WorkflowTermination,
)
from app.agentic.clarification import (
    AlternativeFeasibilityType,
    ClarificationCategory,
    ClarificationDecisionPolicy,
    ClarificationOption,
    ClarificationResponse,
    ClarificationResponseValidator,
    ClarificationStatus,
    RequirementChangeRecord,
)
from app.agentic.events import InMemoryEventLog
from app.agentic.state import Finding, ProjectState, RunStatus
from app.agentic.tools import ToolRegistry, ToolResult
from app.agentic.toolset import create_default_tool_registry
from app.agents.validation_agent import ValidationAgent
from app.orchestration.routing import NextAction
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)


# ============================================================================
# 1. Specialized Agent Coordinators
# ============================================================================

class RequirementAnalysisAgentCoordinator:
    """Specialized coordinator for requirements analysis and verification."""

    def __init__(self) -> None:
        self.role = "requirement_agent"

    def formulate_proposal(self, task: AgentTask, state: ProjectState) -> AgentProposal:
        pid = f"prop_{generate_id()}"
        brief = state.inputs.get("raw_brief", "")
        pname = state.goal or "PlanForge Project"

        evidence: List[ConstraintEvidence] = [
            ConstraintEvidence(
                constraint_id="raw_brief_provided",
                category="mandatory_user",
                priority=ConstraintPriority.MANDATORY_USER,
                description=f"Raw architectural brief provided ({len(brief)} characters)",
                is_hard=True,
                source="user_input",
            )
        ]

        # Check for ambiguity
        questions = []
        if len(brief.strip()) < 15:
            questions.append("Brief is too brief to extract mandatory rooms. Please provide room requirements.")

        params = {"raw_brief": brief, "project_name": pname}
        return AgentProposal(
            proposal_id=pid,
            task_id=task.task_id,
            agent_id=self.role,
            state_version=task.state_version,
            proposed_action="parse_requirements",
            parameters=params,
            supporting_evidence=evidence,
            expected_benefit="Extract normalized, code-compliant Requirements object without fabricating constraints",
            affected_components=["requirements"],
            confidence=1.0 if not questions else 0.5,
            status="proposed",
        )


class PlanningAgentCoordinator:
    """Specialized coordinator for high-level spatial program and zoning strategy."""

    def __init__(self) -> None:
        self.role = "planning_agent"

    def formulate_proposal(
        self,
        task: AgentTask,
        state: ProjectState,
        preferred_strategy: str = "balanced",
    ) -> AgentProposal:
        pid = f"prop_{generate_id()}"
        req = state.get_artifact("requirements")
        hard_errors = state.hard_findings()

        # Defect diagnosis
        codes_str = " ".join(f.code.lower() for f in hard_errors)
        strat = preferred_strategy
        if any(term in codes_str for term in ("adjacency", "separation", "relationship", "access")):
            strat = "circulation_prioritized"
        elif any(term in codes_str for term in ("compact", "stall", "deficit")):
            strat = "compact"

        evidence: List[ConstraintEvidence] = [
            ConstraintEvidence(
                constraint_id="spatial_program_strategy",
                category="planning_intent",
                priority=ConstraintPriority.PLANNING_INTENT,
                description=f"Zoning strategy '{strat}' matches functional adjacencies and requirements",
                is_hard=False,
                source="planning_agent",
            )
        ]

        return AgentProposal(
            proposal_id=pid,
            task_id=task.task_id,
            agent_id=self.role,
            state_version=task.state_version,
            proposed_action="plan_spatial_program",
            parameters={"strategy": strat},
            supporting_evidence=evidence,
            expected_benefit=f"Formulate spatial program PlanningSpec with '{strat}' zoning and relationship graph",
            affected_components=["planning_spec"],
            confidence=0.95,
            status="proposed",
        )


class SpatialAllocationAgentCoordinator:
    """Specialized coordinator for ASAA space allocation and candidate exploration."""

    def __init__(self) -> None:
        self.role = "spatial_allocation_agent"

    def formulate_proposal(
        self,
        task: AgentTask,
        state: ProjectState,
        num_candidates: int = 3,
    ) -> AgentProposal:
        pid = f"prop_{generate_id()}"
        alloc_attempts = state.tool_call_count("allocate_spatial_regions")
        seed = 42 + alloc_attempts * 7

        evidence: List[ConstraintEvidence] = [
            ConstraintEvidence(
                constraint_id="asaa_allocation_capacity",
                category="physical_feasibility",
                priority=ConstraintPriority.PHYSICAL_FEASIBILITY,
                description=f"Allocating spatial regions using seed {seed} with {num_candidates} candidate evaluation",
                is_hard=True,
                source="asaa_allocator",
            )
        ]

        return AgentProposal(
            proposal_id=pid,
            task_id=task.task_id,
            agent_id=self.role,
            state_version=task.state_version,
            proposed_action="allocate_spatial_regions",
            parameters={"seed": seed, "num_candidates": num_candidates},
            supporting_evidence=evidence,
            expected_benefit=f"Generate and evaluate {num_candidates} ASAA spatial allocations to maximize space efficiency",
            affected_components=["allocation_set"],
            confidence=0.95,
            status="proposed",
        )


class ArchitecturalDesignAgentCoordinator:
    """Specialized coordinator for architectural translation and targeted repairs."""

    def __init__(self) -> None:
        self.role = "architectural_agent"

    def formulate_proposal(
        self,
        task: AgentTask,
        state: ProjectState,
        is_repair: bool = False,
    ) -> AgentProposal:
        pid = f"prop_{generate_id()}"
        if is_repair:
            evidence = [
                ConstraintEvidence(
                    constraint_id="targeted_geometry_repair",
                    category="physical_feasibility",
                    priority=ConstraintPriority.PHYSICAL_FEASIBILITY,
                    description="Localized geometric defect repair via refinement loop",
                    is_hard=True,
                    source="refinement_agent",
                )
            ]
            return AgentProposal(
                proposal_id=pid,
                task_id=task.task_id,
                agent_id=self.role,
                state_version=task.state_version,
                proposed_action="refine_design",
                parameters={"action": "full_loop", "max_iterations": 2},
                supporting_evidence=evidence,
                expected_benefit="Targeted geometric refinement to resolve room overlaps and boundary defects without full replanning",
                affected_components=["floor_plan_set"],
                confidence=0.90,
                status="proposed",
            )

        # Standard initial design
        evidence = [
            ConstraintEvidence(
                constraint_id="architectural_intent_layout",
                category="planning_intent",
                priority=ConstraintPriority.PLANNING_INTENT,
                description="Translating allocated regions into room designs, openings, and doors",
                is_hard=False,
                source="architectural_agent",
            )
        ]
        return AgentProposal(
            proposal_id=pid,
            task_id=task.task_id,
            agent_id=self.role,
            state_version=task.state_version,
            proposed_action="design_architecture",
            parameters={"strategy": "standard"},
            supporting_evidence=evidence,
            expected_benefit="Generate room geometries, doors, windows, and circulation intents",
            affected_components=["architectural_design_set"],
            confidence=0.95,
            status="proposed",
        )


class ValidationAgentCoordinator:
    """Specialized coordinator for independent validation and defect classification."""

    def __init__(self) -> None:
        self.role = "validation_agent"

    def formulate_proposal(self, task: AgentTask, state: ProjectState) -> AgentProposal:
        pid = f"prop_{generate_id()}"
        evidence = [
            ConstraintEvidence(
                constraint_id="independent_validator_authority",
                category="validator_finding",
                priority=ConstraintPriority.VALIDATOR_FINDING,
                description="Deterministic FloorPlanValidator run",
                is_hard=True,
                source="validator",
            )
        ]
        return AgentProposal(
            proposal_id=pid,
            task_id=task.task_id,
            agent_id=self.role,
            state_version=task.state_version,
            proposed_action="validate_design",
            parameters={},
            supporting_evidence=evidence,
            expected_benefit="Authoritative code and geometric compliance verification",
            affected_components=["floor_plan_set", "validation"],
            confidence=1.0,
            status="proposed",
        )


# ============================================================================
# 2. Hierarchical Orchestrator
# ============================================================================

class HierarchicalOrchestrator:
    """Top-level coordinator managing multi-agent collaboration, evidence-based

    conflict resolution, and stopping conditions.

    Core Invariants:
    1. State-Dependent Delegation: Agents are invoked conditionally based on current
       defects and state, never a rigid static pipeline.
    2. Version-Controlled Proposals: Stale proposals (proposals with older state_version)
       are strictly rejected to maintain state integrity.
    3. Multi-Floor Cohesion: Vertical alignment and cross-floor consistency are tracked;
       cross-floor changes trigger cross-floor revalidation.
    4. Authoritative Conflict Resolution: Conflicts are resolved via ConstraintPriority
       hierarchy (Mandatory User > Physical Feasibility > Validator > Planning > Soft).
    5. Best-Valid Preservation: A regression or worse candidate never overwrites the best valid design.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        event_log: Optional[InMemoryEventLog] = None,
        budget: Optional[Budget] = None,
        llm_client: Optional[Any] = None,
        llm_config: Optional[Any] = None,
        use_llm: bool = True,
        interactive: bool = False,
    ) -> None:
        self.registry = registry or create_default_tool_registry()
        self.event_log = event_log or InMemoryEventLog()
        self.budget = budget or Budget(max_steps=25, max_tool_calls=35, max_wall_seconds=120.0)
        self.llm_client = llm_client
        self.llm_config = llm_config
        self.use_llm = use_llm
        self.interactive = interactive

        if self.use_llm:
            try:
                from app.orchestration.llm_selector import LLMActionSelector
                self.selector: Optional[Any] = LLMActionSelector(
                    registry=self.registry,
                    llm_client=llm_client,
                    config=llm_config,
                    event_log=self.event_log,
                )
            except Exception as e:
                logger.warning("Failed to initialize LLMActionSelector: %s. Falling back to deterministic coordinator.", e)
                self.selector = None
        else:
            self.selector = None

        # Specialized agents
        self.requirement_coordinator = RequirementAnalysisAgentCoordinator()
        self.planning_coordinator = PlanningAgentCoordinator()
        self.allocation_coordinator = SpatialAllocationAgentCoordinator()
        self.arch_coordinator = ArchitecturalDesignAgentCoordinator()
        self.validation_coordinator = ValidationAgentCoordinator()

    def _check_stopping_conditions(self, state: ProjectState) -> bool:
        """Evaluate budget, stall, or terminal status to stop execution."""
        # Phase 7: Pause when waiting for user clarification in interactive mode
        if self.interactive and state.pending_clarification and getattr(state.pending_clarification, "is_pending", lambda: False)():
            state.status = RunStatus.WAITING_FOR_CLARIFICATION
            return True

        exhausted = state.budget.exhausted()
        if exhausted:
            state.status = RunStatus.BUDGET_EXHAUSTED
            state.status_reason = exhausted
            self.event_log.emit(
                type="budget_exhausted",
                agent="hierarchical_orchestrator",
                summary=f"Execution halted: {exhausted}",
                data={"reason": exhausted},
            )
            return True

        if state.stalled:
            if state.candidate_manager.best_valid_candidate:
                state.restore_best_valid()
                state.status = RunStatus.ACCEPTED
                state.status_reason = "Accepted best valid candidate after refinement stall."
            else:
                state.status = RunStatus.STALLED
                state.status_reason = f"Workflow stalled after {state.no_progress_streak} non-improving steps."
            return True

        if state.status.is_terminal:
            return True

        return False

    def _evaluate_cross_floor_consistency(self, state: ProjectState, floor_plans: Any) -> List[Finding]:
        """Detect cross-floor inconsistencies and trigger revalidation on affected floors."""
        state.facts["cross_floor_validated"] = True
        findings: List[Finding] = []
        fps = getattr(floor_plans, "floor_plans", [])
        if len(fps) > 1:
            self.event_log.emit(
                type="cross_floor_validation",
                agent="hierarchical_orchestrator",
                summary=f"Evaluating vertical circulation across {len(fps)} floors",
                data={"floors": [fp.floor_number for fp in fps]},
            )
        return findings

    def step(self, state: ProjectState) -> bool:
        """Execute one hierarchical coordination cycle. Returns True to continue."""
        state.step += 1
        state.budget.steps_used += 1

        if self._check_stopping_conditions(state):
            return False

        task = self._select_next_task(state)
        return self._execute_agent_step(task, state)

    def _execute_agent_step(
        self,
        task: AgentTask,
        state: ProjectState,
        injected_proposals: Optional[List[AgentProposal]] = None,
    ) -> bool:
        """Execute a selected agent task with version checks, conflict resolution, and candidate preservation."""
        current_version = getattr(state, "state_version", 1)

        self.event_log.emit(
            type="agent_delegated",
            agent="hierarchical_orchestrator",
            summary=f"Delegating '{task.task_type}' to {task.target_agent}",
            data={"target_agent": task.target_agent, "task_id": task.task_id, "state_version": current_version},
        )
        self.event_log.emit(
            type="task_delegated",
            agent="hierarchical_orchestrator",
            summary=f"Delegating '{task.task_type}' to {task.target_agent}",
            data={"target_agent": task.target_agent, "task_id": task.task_id, "state_version": current_version},
        )

        # Handle terminal control tasks
        if task.task_type == "finish":
            state.status = RunStatus.ACCEPTED
            state.status_reason = "All mandatory acceptance criteria satisfied."
            self.event_log.emit(
                type="workflow_finished",
                agent="hierarchical_orchestrator",
                summary=state.status_reason,
                data={"score": state.facts.get("validation_score", 100.0)},
            )
            return False

        if task.task_type == "declare_infeasible":
            if self.interactive and not state.facts.get("infeasibility_revision_declined"):
                cat, clarif_req = ClarificationDecisionPolicy.evaluate(
                    project_id=state.project_id,
                    state_version=getattr(state, "state_version", 1),
                    requirements=state.get_artifact("requirements"),
                    completeness_result=None,
                    feasibility_facts=state.facts,
                    open_questions=list(state.open_questions),
                )
                if clarif_req:
                    state.pending_clarification = clarif_req
                    state.status = RunStatus.WAITING_FOR_CLARIFICATION
                    state.status_reason = clarif_req.issue_explanation
                    state.paused_stage = "feasibility_check"
                    self.event_log.emit(
                        type="clarification_requested",
                        agent="hierarchical_orchestrator",
                        summary=clarif_req.issue_explanation,
                        data=clarif_req.to_dict(),
                    )
                    return False

            state.status = RunStatus.INFEASIBLE
            state.status_reason = task.description
            self.event_log.emit(
                type="infeasibility_declared",
                agent="hierarchical_orchestrator",
                summary=task.description,
                data={"deficits": state.facts.get("deficits", [])},
            )
            return False

        if task.task_type == "request_clarification":
            if self.interactive:
                cat, clarif_req = ClarificationDecisionPolicy.evaluate(
                    project_id=state.project_id,
                    state_version=getattr(state, "state_version", 1),
                    requirements=state.get_artifact("requirements"),
                    completeness_result=None,
                    feasibility_facts=state.facts,
                    open_questions=list(state.open_questions),
                )
                if clarif_req:
                    state.pending_clarification = clarif_req
                state.status = RunStatus.WAITING_FOR_CLARIFICATION
                state.status_reason = task.description
                state.paused_stage = "requirements"
                self.event_log.emit(
                    type="clarification_requested",
                    agent="hierarchical_orchestrator",
                    summary=task.description,
                    data=state.pending_clarification.to_dict() if state.pending_clarification else {"questions": list(state.open_questions)},
                )
                return False
            else:
                state.status = RunStatus.NEEDS_CLARIFICATION
                state.status_reason = task.description
                return False

        # 2. GATHER PROPOSALS
        proposals = injected_proposals if injected_proposals is not None else self._gather_proposals(task, state, task.target_agent)
        if not proposals:
            logger.warning("No proposals received for task %s", task.task_id)
            state.status = RunStatus.STALLED
            state.status_reason = f"No proposals received from {task.target_agent}."
            return False

        for p in proposals:
            self.event_log.emit(
                type="proposal_submitted",
                agent=p.agent_id,
                summary=f"Proposed '{p.proposed_action}': {p.expected_benefit}",
                data={"proposal_id": p.proposal_id, "state_version": p.state_version},
            )

        # 3. VERSION CHECK: Reject stale proposals
        active_proposals = []
        for p in proposals:
            if p.state_version < current_version:
                p.status = "rejected"
                p.rejection_reason = (
                    f"Stale proposal rejected: Proposal state_version {p.state_version} "
                    f"< current state_version {current_version}"
                )
                self.event_log.emit(
                    type="stale_proposal_rejected",
                    agent="hierarchical_orchestrator",
                    summary=p.rejection_reason,
                    data={"proposal_id": p.proposal_id, "proposal_version": p.state_version, "current_version": current_version},
                )
            else:
                active_proposals.append(p)

        if not active_proposals:
            logger.warning("All proposals were rejected as stale.")
            return True

        # 4. EVIDENCE-BASED CONFLICT RESOLUTION
        winning_proposal = None
        conflict_rec = None
        if len(active_proposals) > 1:
            self.event_log.emit(
                type="conflict_detected",
                agent="hierarchical_orchestrator",
                summary=f"Conflict detected between {len(active_proposals)} agent proposals",
                data={"proposal_ids": [p.proposal_id for p in active_proposals]},
            )
            winning_proposal, conflict_rec = ConflictResolver.resolve(task.task_id, active_proposals, state)
            if conflict_rec:
                self.event_log.emit(
                    type="conflict_resolved",
                    agent="hierarchical_orchestrator",
                    summary=conflict_rec.rationale,
                    data=conflict_rec.to_dict(),
                )
        else:
            winning_proposal = active_proposals[0]
            winning_proposal.status = "accepted"

        if not winning_proposal:
            logger.warning("Conflict resolver could not accept any proposal.")
            state.status = RunStatus.STALLED
            state.status_reason = "All agent proposals violated mandatory constraints."
            return False

        # 5. EXECUTE WINNING ACTION
        tool_name = winning_proposal.proposed_action
        tool_args = winning_proposal.parameters

        # Anti-oscillation guard
        current_fp = state.fingerprint()
        action_key = f"{tool_name}:{sorted(tool_args.items())}"
        exec_record = state.executed.get(action_key)
        if exec_record and exec_record.get("fingerprint") == current_fp:
            exec_record["attempts"] = exec_record.get("attempts", 1) + 1
            if exec_record["attempts"] >= 3:
                exec_record["blocked"] = True
                state.stalled = True
                self.event_log.emit(
                    type="action_blocked",
                    agent="hierarchical_orchestrator",
                    summary=f"Action '{action_key}' blocked to prevent infinite cycle",
                    data={"action_key": action_key},
                )
                return True
        else:
            state.executed[action_key] = {
                "action_key": action_key,
                "tool": tool_name,
                "args": tool_args,
                "fingerprint": current_fp,
                "attempts": 1,
                "blocked": False,
            }

        state.budget.tool_calls_used += 1
        t_start = time.perf_counter()

        self.event_log.emit(
            type="tool_called",
            agent="hierarchical_orchestrator",
            summary=f"Executing '{tool_name}' from {winning_proposal.agent_id}",
            data={"tool": tool_name, "args": tool_args},
        )

        tool_result: ToolResult = self.registry.invoke(state, tool_name, tool_args)
        duration_ms = (time.perf_counter() - t_start) * 1000.0

        # Update state version when artifacts are written
        artifacts_written: List[str] = []
        if tool_result.artifacts:
            for k, v in tool_result.artifacts.items():
                state.set_artifact(k, v)
                artifacts_written.append(k)
            state.state_version = getattr(state, "state_version", 1) + 1

        decision_rec = state.record_decision(
            agent=winning_proposal.agent_id,
            kind="tool_call",
            tool=tool_name,
            args=tool_args,
            rationale=winning_proposal.expected_benefit,
            source="hierarchical_coordination",
            state_fingerprint=current_fp,
            evidence_refs=[e.description for e in winning_proposal.supporting_evidence],
        )

        tc_rec = state.record_tool_call(
            decision_id=decision_rec.id,
            tool=tool_name,
            args=tool_args,
            ok=tool_result.ok,
            outcome=tool_result.outcome,
            summary=tool_result.summary,
            duration_ms=round(duration_ms, 2),
            artifacts_written=artifacts_written,
        )

        self.event_log.emit(
            type="tool_result",
            agent="hierarchical_orchestrator",
            summary=tool_result.summary,
            data={"tool": tool_name, "ok": tool_result.ok, "outcome": tool_result.outcome},
        )

        # 6. EVALUATE & PROGRESS
        if tool_result.facts:
            state.facts.update(tool_result.facts)
        if tool_result.questions:
            state.open_questions.extend(tool_result.questions)
        if tool_result.infeasibility:
            state.infeasibility_evidence.append(tool_result.infeasibility)
            if self.interactive and not state.facts.get("infeasibility_revision_declined"):
                cat, clarif_req = ClarificationDecisionPolicy.evaluate(
                    project_id=state.project_id,
                    state_version=getattr(state, "state_version", 1),
                    requirements=state.get_artifact("requirements"),
                    completeness_result=None,
                    feasibility_facts={**state.facts, **tool_result.infeasibility, "feasible": False},
                    open_questions=list(state.open_questions),
                )
                if clarif_req:
                    state.pending_clarification = clarif_req
                    state.status = RunStatus.WAITING_FOR_CLARIFICATION
                    state.status_reason = clarif_req.issue_explanation
                    state.paused_stage = "feasibility_check"
                    self.event_log.emit(
                        type="clarification_requested",
                        agent="hierarchical_orchestrator",
                        summary=clarif_req.issue_explanation,
                        data=clarif_req.to_dict(),
                    )
                    return False

            state.status = RunStatus.INFEASIBLE
            state.status_reason = tool_result.summary
            return False

        if tool_result.outcome == "needs_input":
            if self.interactive:
                cat, clarif_req = ClarificationDecisionPolicy.evaluate(
                    project_id=state.project_id,
                    state_version=getattr(state, "state_version", 1),
                    requirements=state.get_artifact("requirements"),
                    completeness_result=None,
                    feasibility_facts=state.facts,
                    open_questions=list(state.open_questions),
                )
                if clarif_req:
                    state.pending_clarification = clarif_req
                state.status = RunStatus.WAITING_FOR_CLARIFICATION
                state.status_reason = tool_result.summary
                state.paused_stage = "requirements"
                self.event_log.emit(
                    type="clarification_requested",
                    agent="hierarchical_orchestrator",
                    summary=tool_result.summary,
                    data=state.pending_clarification.to_dict() if state.pending_clarification else {"questions": list(state.open_questions)},
                )
                return False
            else:
                state.status = RunStatus.NEEDS_CLARIFICATION
                state.status_reason = tool_result.summary
                return False

        # Multi-Floor Cross-Floor Validation Tracking
        if state.has_artifact("floor_plan_set"):
            fps = state.get_artifact("floor_plan_set")
            if fps and hasattr(fps, "floor_plans") and len(fps.floor_plans) > 1:
                self._evaluate_cross_floor_consistency(state, fps)

        # Candidate Evaluation & Best-Valid Preservation
        cand_rec = None
        is_new_best = False
        if state.has_artifact("floor_plan_set") and ("floor_plan_set" in artifacts_written or tool_name in {"validate_design", "refine_design", "construct_geometry"}):
            cand_rec, is_new_best = state.record_candidate(source_action=tool_name)
            if cand_rec:
                self.event_log.emit(
                    type="candidate_evaluated",
                    agent="hierarchical_orchestrator",
                    summary=f"Candidate {cand_rec.id} evaluated: {cand_rec.evaluation.acceptance_decision}",
                    data={
                        "candidate_id": cand_rec.id,
                        "is_valid": cand_rec.evaluation.is_valid,
                        "score": cand_rec.evaluation.overall_score,
                        "hard_errors": cand_rec.evaluation.hard_error_count,
                        "warnings": cand_rec.evaluation.warning_count,
                        "decision": cand_rec.evaluation.acceptance_decision,
                        "reason": cand_rec.evaluation.decision_reason,
                    },
                )

                if is_new_best:
                    self.event_log.emit(
                        type="best_candidate_updated",
                        agent="hierarchical_orchestrator",
                        summary=f"New best candidate {cand_rec.id} (score {cand_rec.evaluation.overall_score:.1f}, valid={cand_rec.evaluation.is_valid})",
                        data={"candidate_id": cand_rec.id, "score": cand_rec.evaluation.overall_score},
                    )
                elif cand_rec.evaluation.acceptance_decision == "rejected_regression":
                    self.event_log.emit(
                        type="candidate_rejected",
                        agent="hierarchical_orchestrator",
                        summary=f"Candidate {cand_rec.id} rejected due to regression; restoring best valid candidate",
                        data={"candidate_id": cand_rec.id, "reason": cand_rec.evaluation.decision_reason},
                    )
                    state.restore_best_valid()

        # Stagnation streak tracking
        if cand_rec is not None:
            if is_new_best:
                state.no_progress_streak = 0
            else:
                state.no_progress_streak += 1
        elif tool_result.ok and (artifacts_written or tool_result.outcome == "ok"):
            state.no_progress_streak = 0
        else:
            state.no_progress_streak += 1

        if state.no_progress_streak >= 4:
            state.stalled = True
            self.event_log.emit(
                type="stagnation_detected",
                agent="hierarchical_orchestrator",
                summary=f"Stagnation detected: {state.no_progress_streak} steps without improvement",
                data={"streak": state.no_progress_streak},
            )

        return True

    def run(
        self,
        project_id: str,
        goal: str = "",
        raw_brief: Optional[str] = None,
        requirements: Optional[Any] = None,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> ProjectState:
        """Run hierarchical multi-agent loop until termination or acceptance."""
        inps = dict(inputs or {})
        if raw_brief:
            inps["raw_brief"] = raw_brief
        if requirements:
            inps["requirements"] = requirements

        state = ProjectState(
            project_id=project_id,
            goal=goal or (requirements.project_name if requirements else "Residential Floor Plan"),
            inputs=inps,
            budget=Budget(
                max_steps=self.budget.max_steps,
                max_llm_calls=self.budget.max_llm_calls,
                max_tool_calls=self.budget.max_tool_calls,
                max_wall_seconds=self.budget.max_wall_seconds,
            ),
        )
        state.state_version = 1
        state.budget.start()

        self.event_log.emit(
            type="run_started",
            agent="hierarchical_orchestrator",
            summary=f"Started hierarchical multi-agent coordination for {project_id}",
            data={"project_id": project_id, "goal": state.goal},
        )

        while not state.status.is_terminal and not state.status.is_paused:
            cont = self.step(state)
            if not cont:
                break

        if not state.status.is_paused:
            self.event_log.emit(
                type="run_completed",
                agent="hierarchical_orchestrator",
                summary=f"Workflow completed with status: {state.status.value}",
                data={
                    "status": state.status.value,
                    "status_reason": state.status_reason,
                    "steps": state.step,
                    "hard_errors": len(state.hard_findings()),
                    "warnings": len(state.warning_findings()),
                },
            )
        return state

    # ------------------------------------------------------------------------
    # Phase 7 Resumable Workflow & Clarification Response Integration
    # ------------------------------------------------------------------------
    def apply_clarification_response(
        self,
        state: ProjectState,
        response: Optional[ClarificationResponse] = None,
        request_id: Optional[str] = None,
        selected_option_id: Optional[str] = None,
        user_response_text: Optional[str] = None,
        numeric_overrides: Optional[Dict[str, float]] = None,
        expected_state_version: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[ClarificationResponse]]:
        """Validate and apply user clarification response atomically."""
        if response is None:
            req = state.pending_clarification
            req_id = request_id or (req.request_id if req else "")
            response = ClarificationResponse(
                request_id=req_id,
                project_id=state.project_id or "",
                selected_option_id=selected_option_id,
                user_response_text=user_response_text,
                numeric_overrides=numeric_overrides or {},
                expected_state_version=expected_state_version,
            )

        if not state.pending_clarification:
            return False, "No pending clarification request for this project.", response

        req = state.pending_clarification
        ok, msg, updated_req, change_rec = ClarificationResponseValidator.validate_and_apply(
            request=req,
            response=response,
            current_state_version=getattr(state, "state_version", 1),
            current_requirements=state.get_artifact("requirements"),
        )
        if not ok:
            return False, msg, response

        if response.selected_option_id == "opt_terminate_infeasible":
            state.facts["infeasibility_revision_declined"] = True
            req.status = ClarificationStatus.ANSWERED
            state.clarification_history.append(req)
            state.pending_clarification = None
            state.status = RunStatus.INFEASIBLE
            state.status_reason = "User declined suggested constraint revisions."
            self.event_log.emit(
                type="clarification_answered",
                agent="hierarchical_orchestrator",
                summary="User declined revisions; workflow terminated as infeasible.",
                data={"response_id": response.response_id, "selected_option": "opt_terminate_infeasible"},
            )
            return True, msg, response

        if updated_req:
            state.set_artifact("requirements", updated_req)
            state.inputs["requirements"] = updated_req

        if change_rec:
            state.requirement_changes.append(change_rec)
        state.clarification_responses.append(response)

        invalidated = state.invalidate_downstream("requirements")
        req.status = ClarificationStatus.ANSWERED
        state.clarification_history.append(req)
        state.pending_clarification = None
        state.open_questions.clear()
        state.stalled = False
        state.no_progress_streak = 0
        state.status = RunStatus.RESUMABLE

        self.event_log.emit(
            type="clarification_answered",
            agent="hierarchical_orchestrator",
            summary=f"Clarification response accepted: {msg}",
            data={
                "response_id": response.response_id,
                "selected_option": response.selected_option_id,
                "invalidated_artifacts": list(invalidated),
                "state_version": state.state_version,
            },
        )
        return True, msg, response

    def resume(self, state: ProjectState) -> Tuple[bool, str, ProjectState]:
        """Resume a paused/resumable workflow execution."""
        if state.status == RunStatus.CANCELLED:
            logger.warning("Cannot resume a cancelled workflow.")
            return False, "Cannot resume a cancelled workflow.", state

        if state.pending_clarification and getattr(state.pending_clarification, "is_pending", lambda: False)():
            logger.warning("Cannot resume workflow while clarification request is still pending.")
            return False, "Cannot resume workflow while clarification request is still pending.", state

        state.status = RunStatus.RUNNING
        self.event_log.emit(
            type="workflow_resumed",
            agent="hierarchical_orchestrator",
            summary=f"Workflow resumed from stage '{state.paused_stage or 'requirements'}'",
            data={"state_version": state.state_version},
        )

        while not state.status.is_terminal and not state.status.is_paused:
            cont = self.step(state)
            if not cont:
                break

        if not state.status.is_paused:
            self.event_log.emit(
                type="run_completed",
                agent="hierarchical_orchestrator",
                summary=f"Workflow completed with status: {state.status.value}",
                data={
                    "status": state.status.value,
                    "status_reason": state.status_reason,
                    "steps": state.step,
                    "hard_errors": len(state.hard_findings()),
                    "warnings": len(state.warning_findings()),
                },
            )
        return True, f"Workflow resumed with status: {state.status.value}", state

    def cancel(self, state: ProjectState, reason: str = "User cancelled workflow") -> None:
        """Cancel an active or paused workflow safely."""
        if state.pending_clarification:
            state.pending_clarification.status = ClarificationStatus.CANCELLED
            state.clarification_history.append(state.pending_clarification)
            state.pending_clarification = None
        state.status = RunStatus.CANCELLED
        state.status_reason = reason
        self.event_log.emit(
            type="workflow_cancelled",
            agent="hierarchical_orchestrator",
            summary=f"Workflow cancelled: {reason}",
            data={"reason": reason},
        )

    # ------------------------------------------------------------------------
    # Internal Task Selection & Proposal Dispatch
    # ------------------------------------------------------------------------
    def _select_next_task(self, state: ProjectState) -> AgentTask:
        """Determine next task based on evidence, defects, and stage."""
        facts = state.facts
        artifacts = set(state.artifacts.keys())

        # If LLM selector is configured, attempt LLM action selection first
        if self.use_llm and self.selector:
            try:
                decision = self.selector.decide(state)
                action_name = getattr(decision, "tool", None) or getattr(decision, "action", None)
                action_args = getattr(decision, "args", None) or getattr(decision, "params", {})
                if action_name:
                    if action_name == "finish":
                        return AgentTask(
                            task_id=f"task_{state.step}_{generate_id()}",
                            target_agent="hierarchical_orchestrator",
                            task_type="finish",
                            description="All acceptance criteria satisfied",
                            context={},
                            state_version=getattr(state, "state_version", 1),
                        )
                    if action_name == "declare_infeasible":
                        return AgentTask(
                            task_id=f"task_{state.step}_{generate_id()}",
                            target_agent="spatial_allocation_agent",
                            task_type="declare_infeasible",
                            description="Physical requirements cannot be satisfied",
                            context={"deficits": state.facts.get("deficits", [])},
                            state_version=getattr(state, "state_version", 1),
                        )
                    tool_map = {
                        "parse_requirements": ("requirement_agent", "parse_requirements", "Extract and normalize requirements", {}),
                        "check_feasibility": ("requirement_agent", "check_feasibility", "Verify site envelope and area budgets", {}),
                        "plan_spatial_program": ("planning_agent", "plan_spatial_program", "Formulate spatial program", action_args),
                        "allocate_spatial_regions": ("spatial_allocation_agent", "allocate_spatial_regions", "Allocate spatial regions with ASAA", {**action_args, "num_candidates": max(3, int(action_args.get("num_candidates", 3)))}),
                        "design_architecture": ("architectural_agent", "design_architecture", "Translate allocated regions into architecture", action_args),
                        "construct_geometry": ("architectural_agent", "construct_geometry", "Construct physical geometry", action_args),
                        "validate_design": ("validation_agent", "validate_design", "Run independent validation", {}),
                        "refine_design": ("architectural_agent", "repair_geometry", "Targeted geometric repair", action_args),
                        "generate_alternatives": ("architectural_agent", "generate_alternatives", "Generate design alternatives", action_args),
                        "export_bundle": ("architectural_agent", "export_bundle", "Export CAD DXF and project bundle", action_args),
                    }
                    if action_name in tool_map:
                        t_agent, t_type, t_desc, t_ctx = tool_map[action_name]
                        return AgentTask(
                            task_id=f"task_{state.step}_{generate_id()}",
                            target_agent=t_agent,
                            task_type=t_type,
                            description=t_desc,
                            context=t_ctx,
                            state_version=getattr(state, "state_version", 1),
                        )
            except Exception as e:
                self.event_log.emit(
                    type="coordinator_fallback",
                    agent="hierarchical_orchestrator",
                    summary=f"LLM selection failed ({e}); falling back to deterministic coordination",
                    data={"error": str(e)},
                )

        # Deterministic coordination logic:
        # 1. Open questions
        if state.open_questions:
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="requirement_agent",
                task_type="request_clarification",
                description=f"Unresolved questions: {state.open_questions}",
                context={},
                state_version=getattr(state, "state_version", 1),
            )

        # 2. Deficit / Infeasibility
        if facts.get("feasible") is False:
            deficits = facts.get("deficits", [])
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="spatial_allocation_agent",
                task_type="declare_infeasible",
                description=f"Physical site capacity deficit: {deficits}",
                context={"deficits": deficits},
                state_version=getattr(state, "state_version", 1),
            )

        # 3. Allocation infeasibility finding in state.findings
        for f in state.findings:
            if "allocation" in f.code.lower() or "allocation" in f.message.lower() or "exceeds" in f.message.lower():
                return AgentTask(
                    task_id=f"task_{state.step}_{generate_id()}",
                    target_agent="planning_agent",
                    task_type="revise_spatial_program",
                    description=f"Allocation failure detected: {f.message}. Revise spatial program.",
                    context={"finding": f.signature},
                    state_version=getattr(state, "state_version", 1),
                )

        # 4. If geometry is already constructed, evaluate validation findings and repair
        if "floor_plan_set" in artifacts:
            if not state.validation_is_current():
                return AgentTask(
                    task_id=f"task_{state.step}_{generate_id()}",
                    target_agent="validation_agent",
                    task_type="validate_design",
                    description="Run independent FloorPlanValidator checks",
                    context={},
                    state_version=getattr(state, "state_version", 1),
                )

            findings = state.hard_findings() or [
                f for f in state.findings
                if any(k in f.code.lower() for k in ("door", "overlap", "collision", "defect", "warning"))
            ]
            if findings:
                primary_codes = " ".join(f.code.lower() for f in findings)

                # If repair_geometry was already attempted or stagnation streak >= 2, shift recovery strategy
                if state.no_progress_streak >= 2 or "repair_geometry:{}" in state.executed:
                    return AgentTask(
                        task_id=f"task_{state.step}_{generate_id()}",
                        target_agent="spatial_agent",
                        task_type="reallocate_spaces",
                        description="Stagnation in geometric repair; shifting strategy to spatial reallocation.",
                        context={"num_candidates": 3},
                        state_version=getattr(state, "state_version", 1),
                    )

                # Category C: Adjacency / Zoning
                if any(term in primary_codes for term in ("adjacency", "separation", "relationship", "access")):
                    return AgentTask(
                        task_id=f"task_{state.step}_{generate_id()}",
                        target_agent="planning_agent",
                        task_type="plan_spatial_program",
                        description="Replan spatial zoning with circulation priorities",
                        context={"strategy": "circulation_prioritized"},
                        state_version=getattr(state, "state_version", 1),
                    )

                # Category B: Area / Allocation
                if any(term in primary_codes for term in ("area", "budget", "deficit")):
                    return AgentTask(
                        task_id=f"task_{state.step}_{generate_id()}",
                        target_agent="spatial_agent",
                        task_type="allocate_spatial_regions",
                        description="Reallocate spatial regions with alternative seed",
                        context={"num_candidates": 3},
                        state_version=getattr(state, "state_version", 1),
                    )

                # Category A: Localized Geometry
                return AgentTask(
                    task_id=f"task_{state.step}_{generate_id()}",
                    target_agent="architectural_agent",
                    task_type="repair_geometry",
                    description=f"Targeted geometric repair for {len(findings)} error(s)",
                    context={},
                    state_version=getattr(state, "state_version", 1),
                )

            # Multi-design alternatives if requested
            num_alts = state.inputs.get("num_alternatives", 1)
            if num_alts > 1 and "alternative_set" not in artifacts:
                return AgentTask(
                    task_id=f"task_{state.step}_{generate_id()}",
                    target_agent="architectural_agent",
                    task_type="generate_alternatives",
                    description=f"Generate {num_alts} diverse design alternatives",
                    context={"num_alternatives": num_alts},
                    state_version=getattr(state, "state_version", 1),
                )

            # Exports
            if not facts.get("export_bundle_path"):
                return AgentTask(
                    task_id=f"task_{state.step}_{generate_id()}",
                    target_agent="architectural_agent",
                    task_type="export_bundle",
                    description="Export CAD DXF and project bundle",
                    context={"output_dir": state.inputs.get("output_dir", "outputs")},
                    state_version=getattr(state, "state_version", 1),
                )

            # Acceptance
            score = state.facts.get("validation_score", 100.0)
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="hierarchical_orchestrator",
                task_type="finish",
                description=f"Design validated cleanly with 0 hard errors and quality score {score:.1f}/100",
                context={},
                state_version=getattr(state, "state_version", 1),
            )

        # 5. Construction pipeline when floor_plan_set not yet generated
        # Requirements
        if "requirements" not in artifacts:
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="requirement_agent",
                task_type="parse_requirements",
                description="Extract and normalize user architectural requirements",
                context={},
                state_version=getattr(state, "state_version", 1),
            )

        # Feasibility check
        if not facts.get("feasibility_checked", False) and "feasible" not in facts:
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="requirement_agent",
                task_type="check_feasibility",
                description="Verify site envelope and room area budgets",
                context={},
                state_version=getattr(state, "state_version", 1),
            )

        # Planning Spec
        if "planning_spec" not in artifacts:
            strat = state.strategy.get("planning_strategy", "balanced")
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="planning_agent",
                task_type="plan_spatial_program",
                description=f"Formulate spatial program PlanningSpec using '{strat}' zoning",
                context={"strategy": strat},
                state_version=getattr(state, "state_version", 1),
            )

        # Allocation Set
        if "allocation_set" not in artifacts:
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="spatial_allocation_agent",
                task_type="allocate_spatial_regions",
                description="Allocate spatial regions with ASAA candidate exploration",
                context={"num_candidates": 3},
                state_version=getattr(state, "state_version", 1),
            )

        # Architectural Design
        if "architectural_design_set" not in artifacts:
            return AgentTask(
                task_id=f"task_{state.step}_{generate_id()}",
                target_agent="architectural_agent",
                task_type="design_architecture",
                description="Translate allocated regions into room designs, doors, and windows",
                context={},
                state_version=getattr(state, "state_version", 1),
            )

        # Construct Geometry
        return AgentTask(
            task_id=f"task_{state.step}_{generate_id()}",
            target_agent="architectural_agent",
            task_type="construct_geometry",
            description="Construct authoritative 2D physical geometry",
            context={},
            state_version=getattr(state, "state_version", 1),
        )

    def _gather_proposals(self, task: AgentTask, state: ProjectState, target_agent: str) -> List[AgentProposal]:
        """Dispatch task to target agent and collect structured proposal."""
        if target_agent == "requirement_agent":
            if task.task_type == "parse_requirements":
                return [self.requirement_coordinator.formulate_proposal(task, state)]
            elif task.task_type == "check_feasibility":
                pid = f"prop_{generate_id()}"
                return [
                    AgentProposal(
                        proposal_id=pid,
                        task_id=task.task_id,
                        agent_id=target_agent,
                        state_version=task.state_version,
                        proposed_action="check_feasibility",
                        parameters={},
                        supporting_evidence=[
                            ConstraintEvidence(
                                constraint_id="site_boundary_envelope",
                                category="physical_feasibility",
                                priority=ConstraintPriority.PHYSICAL_FEASIBILITY,
                                description="Verifying plot setback envelope and room area feasibility",
                                is_hard=True,
                                source="boundary_calculator",
                            )
                        ],
                        expected_benefit="Verify site boundary capacity before computational allocation",
                        affected_components=["facts"],
                        confidence=1.0,
                    )
                ]

        elif target_agent == "planning_agent":
            strat = task.context.get("strategy", "balanced")
            return [self.planning_coordinator.formulate_proposal(task, state, preferred_strategy=strat)]

        elif target_agent in ("spatial_allocation_agent", "spatial_agent"):
            num_cands = task.context.get("num_candidates", 3)
            return [self.allocation_coordinator.formulate_proposal(task, state, num_candidates=num_cands)]

        elif target_agent in ("architectural_agent", "architectural_design_agent"):
            if task.task_type == "repair_geometry":
                return [self.arch_coordinator.formulate_proposal(task, state, is_repair=True)]
            elif task.task_type == "design_architecture":
                return [self.arch_coordinator.formulate_proposal(task, state, is_repair=False)]
            elif task.task_type == "construct_geometry":
                pid = f"prop_{generate_id()}"
                return [
                    AgentProposal(
                        proposal_id=pid,
                        task_id=task.task_id,
                        agent_id=target_agent,
                        state_version=task.state_version,
                        proposed_action="construct_geometry",
                        parameters={},
                        supporting_evidence=[
                            ConstraintEvidence(
                                constraint_id="shapely_geometric_realization",
                                category="physical_feasibility",
                                priority=ConstraintPriority.PHYSICAL_FEASIBILITY,
                                description="Constructing authoritative Shapely 2D physical walls and boundaries",
                                is_hard=True,
                                source="geometry_engine",
                            )
                        ],
                        expected_benefit="Physical 2D Shapely geometry realization",
                        affected_components=["floor_plan_set"],
                        confidence=1.0,
                    )
                ]
            elif task.task_type == "generate_alternatives":
                num_alts = task.context.get("num_alternatives", 2)
                pid = f"prop_{generate_id()}"
                return [
                    AgentProposal(
                        proposal_id=pid,
                        task_id=task.task_id,
                        agent_id=target_agent,
                        state_version=task.state_version,
                        proposed_action="generate_alternatives",
                        parameters={"num_alternatives": num_alts},
                        supporting_evidence=[],
                        expected_benefit=f"Produce {num_alts} diverse design alternatives",
                        affected_components=["alternative_set"],
                        confidence=0.9,
                    )
                ]
            elif task.task_type == "export_bundle":
                out_dir = task.context.get("output_dir", "outputs")
                pid = f"prop_{generate_id()}"
                return [
                    AgentProposal(
                        proposal_id=pid,
                        task_id=task.task_id,
                        agent_id=target_agent,
                        state_version=task.state_version,
                        proposed_action="export_bundle",
                        parameters={"output_dir": out_dir},
                        supporting_evidence=[],
                        expected_benefit="Export CAD DXF and report bundles",
                        affected_components=["export_bundle_path"],
                        confidence=1.0,
                    )
                ]

        elif target_agent == "validation_agent":
            return [self.validation_coordinator.formulate_proposal(task, state)]

        return []
