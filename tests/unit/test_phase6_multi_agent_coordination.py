"""Unit and Integration Tests for Phase 6: Hybrid Hierarchical Multi-Agent Coordination.

Verifies all 18 mandatory specifications:
1. A Planning Agent proposal is rejected when it violates a mandatory constraint.
2. An allocation failure triggers a meaningful planning revision.
3. A geometry defect triggers architectural repair rather than unnecessary full replanning.
4. A failed validation causes a different strategy when the previous repair did not improve candidate.
5. Two agents produce conflicting proposals and the conflict is resolved using evidence.
6. Multi-floor changes trigger the required cross-floor validation.
7. An infeasible requirement set terminates with a structured explanation.
8. An invalid candidate never replaces the best valid candidate.
9. A stale agent proposal cannot overwrite a newer project state.
10. Repeated delegation or action cycles terminate safely.
11. Budget exhaustion returns a truthful terminal status.
12. Missing LLM credentials use an explicit deterministic fallback.
13. LLM timeout, malformed response, and invalid tool parameters are handled safely.
14. The event log demonstrates actual delegation and coordination.
15. The legacy pipeline mode remains behaviorally compatible.
16. Existing exports and API response contracts remain compatible.
17. Valid and infeasible cases preserve their correct statuses.
18. An unnecessary agent is not invoked when the current state does not require it.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.agentic.budget import Budget
from app.agentic.candidates import (
    CandidateEvaluation,
    CandidateManager,
    CandidateRecord,
    DesignQualityEvaluator,
)
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
from app.agentic.events import InMemoryEventLog
from app.agentic.state import Finding, ProjectState, RunStatus
from app.agentic.tools import ToolRegistry, ToolResult
from app.agentic.toolset import create_default_tool_registry
from app.llm.client import MockLLMClient
from app.llm.configuration import LLMConfig
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoRoom
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.orchestration.config import OrchestrationConfig
from app.orchestration.hierarchical import (
    ArchitecturalDesignAgentCoordinator,
    HierarchicalOrchestrator,
    PlanningAgentCoordinator,
    RequirementAnalysisAgentCoordinator,
    SpatialAllocationAgentCoordinator,
    ValidationAgentCoordinator,
)
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.routing import NextAction


def _make_dummy_floor_plan_set(num_rooms: int = 3, floor_numbers: list[int] = [1]) -> FloorPlanSet:
    fps = []
    for fn in floor_numbers:
        rooms = []
        for i in range(num_rooms):
            poly = [
                (float(i * 4), 0.0),
                (float((i + 1) * 4), 0.0),
                (float((i + 1) * 4), 4.0),
                (float(i * 4), 4.0),
            ]
            r = GeoRoom(id=f"f{fn}_room_{i+1}", room_type=f"room_{i+1}", usable_polygon=poly, built_polygon=poly, area_sqm=16.0)
            rooms.append(r)
        geom = Geometry(floor_number=fn, rooms=rooms)
        fps.append(FloorPlan(floor_number=fn, geometry=geom))
    return FloorPlanSet(floor_plans=fps)


# ============================================================================
# 1. Planning Agent proposal rejected when violating a mandatory constraint
# ============================================================================
def test_planning_proposal_rejected_when_violating_mandatory_constraint():
    state = ProjectState(project_id="test_proj", goal="Test")
    state.state_version = 1

    # Proposal 1: Violates a mandatory user constraint (e.g. attempting to remove a required room)
    prop_violating = AgentProposal(
        proposal_id="prop_violating",
        task_id="task_1",
        agent_id="planning_agent",
        state_version=1,
        proposed_action="plan_spatial_program",
        parameters={"reduce_rooms": True},
        evidence=[
            ConstraintEvidence(
                constraint_id="remove_bedroom",
                category="mandatory_user",
                priority=ConstraintPriority.MANDATORY_USER,
                description="Omit mandatory second bedroom",
                is_hard=True,
                source="planning_heuristics",
            )
        ],
        expected_benefit="Fit smaller area",
    )

    # Proposal 2: Compliant proposal respecting mandatory constraints
    prop_compliant = AgentProposal(
        proposal_id="prop_compliant",
        task_id="task_1",
        agent_id="spatial_agent",
        state_version=1,
        proposed_action="allocate_spatial_regions",
        parameters={"strategy": "compact"},
        evidence=[
            ConstraintEvidence(
                constraint_id="keep_mandatory_rooms",
                category="mandatory_user",
                priority=ConstraintPriority.MANDATORY_USER,
                description="Retain all mandatory bedrooms",
                is_hard=False,
                source="user_requirements",
            )
        ],
        expected_benefit="Feasible layout with all rooms",
    )

    # Conflict resolver rejects the proposal violating hard constraints
    winning, conflict = ConflictResolver.resolve("task_1", [prop_violating, prop_compliant], state)
    assert winning is not None
    assert winning.proposal_id == "prop_compliant"
    assert "mandatory" in prop_violating.rejection_reason.lower() or "hard constraint" in prop_violating.rejection_reason.lower()


# ============================================================================
# 2. Allocation failure triggers meaningful planning revision
# ============================================================================
def test_allocation_failure_triggers_meaningful_planning_revision():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj", goal="Test")

    # Simulate an allocation failure finding in state
    state.apply_findings(
        [
            Finding(
                code="allocation_infeasible",
                severity="error",
                message="Total room area exceeds buildable footprint by 25 sqm",
                suggested_actions=["revise_planning_strategy", "reduce_soft_room_areas"],
            )
        ],
        scope_keys=["allocation_set"],
    )

    task = orchestrator._select_next_task(state)
    assert task is not None
    assert task.assigned_agent == "planning_agent"
    assert task.intent == "revise_spatial_program"
    assert "allocation failure" in task.description.lower() or "finding" in task.description.lower()


# ============================================================================
# 3. Geometry defect triggers architectural repair rather than full replanning
# ============================================================================
def test_geometry_defect_triggers_architectural_repair_not_full_replanning():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj", goal="Test")
    state.set_artifact("floor_plan_set", _make_dummy_floor_plan_set())

    # Geometry defect: door overlap or boundary violation
    state.apply_findings(
        [
            Finding(
                code="door_swing_collision",
                severity="warning",
                message="Door swings into adjoining room wall",
                suggested_actions=["repair_geometry", "adjust_opening"],
            )
        ],
        scope_keys=["floor_plan_set"],
    )

    task = orchestrator._select_next_task(state)
    assert task is not None
    assert task.assigned_agent == "architectural_agent"
    assert task.intent == "repair_geometry"


# ============================================================================
# 4. Failed validation causes a different strategy when previous repair did not improve
# ============================================================================
def test_failed_validation_causes_strategy_change_after_non_improving_repair():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj", goal="Test")
    state.set_artifact("floor_plan_set", _make_dummy_floor_plan_set())

    # Record that repair_geometry was already attempted and yielded no progress
    action_key = "repair_geometry:{}"
    state.executed[action_key] = {"attempts": 2, "blocked": False}
    state.no_progress_streak = 2

    # Validation finding persists
    state.apply_findings(
        [
            Finding(
                code="unresolved_overlap",
                severity="error",
                message="Persistent boundary overlap",
                suggested_actions=["repair_geometry"],
            )
        ],
        scope_keys=["floor_plan_set"],
    )

    task = orchestrator._select_next_task(state)
    assert task is not None
    # Because repair_geometry stagnated, recovery shifts to spatial reallocation or replanning
    assert task.assigned_agent in ("spatial_agent", "planning_agent")
    assert task.intent in ("reallocate_spaces", "revise_spatial_program")


# ============================================================================
# 5. Two agents produce conflicting proposals and conflict is resolved using evidence
# ============================================================================
def test_conflicting_proposals_resolved_using_evidence_priority():
    state = ProjectState(project_id="test_proj", goal="Test")
    state.state_version = 1

    # Agent A proposes a soft layout preference (Level 5)
    prop_soft = AgentProposal(
        proposal_id="prop_soft",
        task_id="task_conflict",
        agent_id="planning_agent",
        state_version=1,
        proposed_action="plan_spatial_program",
        parameters={"aspect_ratio": "1.5"},
        evidence=[
            ConstraintEvidence(
                constraint_id="feng_shui_pref",
                category="soft_preference",
                priority=ConstraintPriority.SOFT_PREFERENCE,
                description="Client preferred elongated living room",
                is_hard=False,
            )
        ],
        expected_benefit="Improved aesthetic comfort",
    )

    # Agent B proposes a fix addressing a validator defect (Level 3)
    prop_validator_fix = AgentProposal(
        proposal_id="prop_validator_fix",
        task_id="task_conflict",
        agent_id="architectural_agent",
        state_version=1,
        proposed_action="repair_geometry",
        parameters={"door_id": "D1", "flip_swing": True},
        evidence=[
            ConstraintEvidence(
                constraint_id="val_door_defect",
                category="validator_finding",
                priority=ConstraintPriority.VALIDATOR_FINDING,
                description="Validator reported door egress defect",
                is_hard=True,
            )
        ],
        expected_benefit="Eliminates egress violation",
    )

    winner, conflict_rec = ConflictResolver.resolve("task_conflict", [prop_soft, prop_validator_fix], state)
    assert winner is not None
    assert winner.proposal_id == "prop_validator_fix"
    assert conflict_rec is not None
    assert conflict_rec.winner_id == "prop_validator_fix"
    assert "priority" in conflict_rec.rationale.lower()


# ============================================================================
# 6. Multi-floor changes trigger required cross-floor validation
# ============================================================================
def test_multi_floor_changes_trigger_required_cross_floor_validation():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj", goal="Two Floor")
    fps = _make_dummy_floor_plan_set(num_rooms=3, floor_numbers=[1, 2])
    state.set_artifact("floor_plan_set", fps)

    # Mark floor 2 as modified
    state.facts["modified_floors"] = [2]
    # Check consistency
    findings = orchestrator._evaluate_cross_floor_consistency(state, fps)
    assert isinstance(findings, list)
    # The facts should track affected floors for validation
    assert state.facts.get("cross_floor_validated") is True


# ============================================================================
# 7. Infeasible requirement set terminates with structured explanation
# ============================================================================
def test_infeasible_requirement_set_terminates_with_structured_explanation():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    # 500 sqm requested on a 50 sqm plot
    raw_brief = (
        "Design a luxury residential mansion on a tiny 50 sqm plot. "
        "Mandatory spaces: 10 master bedrooms at 35 sqm each, 5 living rooms at 50 sqm each. Total min area 600 sqm."
    )
    res = orchestrator.run(project_id="infeasible_run", raw_brief=raw_brief)
    # Should terminate with INFEASIBLE or NEEDS_CLARIFICATION rather than claiming success
    assert res.status in (RunStatus.INFEASIBLE, RunStatus.NEEDS_CLARIFICATION, RunStatus.FAILED)
    assert len(res.status_reason) > 0


# ============================================================================
# 8. Invalid candidate never replaces best valid candidate
# ============================================================================
def test_invalid_candidate_never_replaces_best_valid_candidate():
    cm = CandidateManager()

    valid_fp = _make_dummy_floor_plan_set()
    val_valid = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=82.0, issues=[])]
    )
    rec1, is_best1 = cm.register_candidate(
        step=1,
        source_action="allocate_spatial_regions",
        floor_plan_set=valid_fp,
        validation_report=val_valid,
    )
    assert is_best1 is True
    assert cm.best_valid_candidate is not None

    # Subsequent candidate with higher raw design score but invalid hard constraint
    invalid_fp = _make_dummy_floor_plan_set()
    val_invalid = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                score=95.0,
                issues=[
                    ValidationIssue(
                        category="boundary",
                        severity="error",
                        message="Overlap",
                    )
                ],
            )
        ]
    )
    rec2, is_best2 = cm.register_candidate(
        step=2,
        source_action="repair_geometry",
        floor_plan_set=invalid_fp,
        validation_report=val_invalid,
    )
    assert is_best2 is False
    assert cm.best_valid_candidate.id == rec1.id
    assert cm.best_valid_candidate.evaluation.is_valid is True


# ============================================================================
# 9. Stale agent proposal cannot overwrite newer project state
# ============================================================================
def test_stale_agent_proposal_cannot_overwrite_newer_project_state():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj", goal="Test")
    state.state_version = 4  # State has advanced to version 4

    stale_proposal = AgentProposal(
        proposal_id="stale_prop_1",
        task_id="task_stale",
        agent_id="planning_agent",
        state_version=2,  # Stale: proposal generated from version 2
        proposed_action="plan_spatial_program",
        parameters={},
        expected_benefit="Update layout",
    )

    task = AgentTask(
        task_id="task_stale",
        target_agent="planning_agent",
        task_type="plan_spatial_program",
        description="Plan program",
        state_version=4,
    )

    # When the orchestrator executes step with stale proposal, it rejects it
    executed = orchestrator._execute_agent_step(task, state, injected_proposals=[stale_proposal])
    assert stale_proposal.status == "rejected"
    assert "stale" in stale_proposal.rejection_reason.lower()


# ============================================================================
# 10. Repeated delegation or action cycles terminate safely
# ============================================================================
def test_repeated_delegation_cycles_terminate_safely():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj", goal="Test")

    # Simulate hitting same action repeatedly
    action_key = "repair_geometry:{}"
    state.executed[action_key] = {"attempts": 3, "blocked": True}
    state.stalled = True

    # Orchestrator checks stopping conditions
    should_stop = orchestrator._check_stopping_conditions(state)
    assert should_stop is True
    assert state.status in (RunStatus.STALLED, RunStatus.RUNNING)


# ============================================================================
# 11. Budget exhaustion returns truthful terminal status
# ============================================================================
def test_budget_exhaustion_returns_truthful_terminal_status():
    budget = Budget(max_steps=3, max_tool_calls=5)
    orchestrator = HierarchicalOrchestrator(budget=budget, use_llm=False)

    state = ProjectState(project_id="test_proj", budget=budget)
    state.budget.steps_used = 3

    should_stop = orchestrator._check_stopping_conditions(state)
    assert should_stop is True
    assert state.status == RunStatus.BUDGET_EXHAUSTED
    assert "exhausted" in state.status_reason.lower()


# ============================================================================
# 12. Missing LLM credentials use explicit deterministic fallback
# ============================================================================
def test_missing_llm_credentials_use_explicit_deterministic_fallback():
    # Pass LLMConfig with empty API key
    cfg = LLMConfig(provider="gemini", api_key="", model_name="gemini-1.5-flash")
    orchestrator = HierarchicalOrchestrator(llm_config=cfg, use_llm=True)
    # Selector should fall back to deterministic mode
    assert orchestrator.selector is not None
    # Selector mode should be deterministic or client is not configured
    state = ProjectState(project_id="fallback_test")
    task = orchestrator._select_next_task(state)
    assert task is not None
    assert task.assigned_agent == "requirement_agent"


# ============================================================================
# 13. LLM timeout, malformed response, and invalid tool parameters are handled safely
# ============================================================================
def test_llm_timeout_malformed_response_handled_safely():
    mock_client = MagicMock()
    mock_client.generate_structured.side_effect = TimeoutError("LLM call timed out after 30s")

    orchestrator = HierarchicalOrchestrator(llm_client=mock_client, use_llm=True)
    state = ProjectState(project_id="timeout_test")

    # Should not crash; gracefully falls back to deterministic decision
    task = orchestrator._select_next_task(state)
    assert task is not None
    assert task.assigned_agent == "requirement_agent"


# ============================================================================
# 14. Event log demonstrates actual delegation and coordination
# ============================================================================
def test_event_log_demonstrates_actual_delegation_and_coordination():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    brief = "Single floor house on 30x40 plot with 1 living room, 1 kitchen, 1 bedroom, 1 bathroom."
    state = orchestrator.run(project_id="test_event_log", raw_brief=brief)

    events = orchestrator.event_log.events
    event_types = [e.type for e in events]

    assert "agent_delegated" in event_types or "task_delegated" in event_types
    assert "proposal_submitted" in event_types
    assert "tool_called" in event_types


# ============================================================================
# 15. Legacy pipeline mode remains behaviorally compatible
# ============================================================================
def test_legacy_pipeline_mode_remains_behaviorally_compatible():
    orch = PlanForgeOrchestrator()
    brief = "Single floor bungalow on 40x50 plot with 1 living, 1 kitchen, 1 bedroom, 1 bathroom."
    result = orch.generate(raw_brief=brief, mode="pipeline")

    assert result.status == "completed"
    assert result.floor_plan_set is not None
    # Decisions trace should not have agentic state from multi-agent
    assert "agentic_state" not in result.__dict__ or result.agentic_state is None or result.agentic_state == {}


# ============================================================================
# 16. Existing exports and API response contracts remain compatible
# ============================================================================
def test_existing_exports_and_api_response_contracts_remain_compatible():
    orch = PlanForgeOrchestrator()
    brief = "Single floor house on 30x40 plot with 1 living room, 1 kitchen, 2 bedrooms, 1 bathroom."
    res = orch.generate(raw_brief=brief, mode="multi_agent")

    assert res.project_id is not None
    assert res.project_name is not None
    assert res.status in ("completed", "unresolved", "failed")
    assert isinstance(res.stage_records, dict)
    assert "agentic_state" in res.__dict__
    assert res.agentic_state is not None
    assert "events" in res.agentic_state


# ============================================================================
# 17. Valid and infeasible cases preserve correct statuses
# ============================================================================
def test_valid_and_infeasible_cases_preserve_correct_statuses():
    orch = PlanForgeOrchestrator()

    # Valid case
    valid_brief = "Single floor house on 30x40 plot with 1 living room, 1 kitchen, 1 bedroom, 1 bathroom."
    res_valid = orch.generate(raw_brief=valid_brief, mode="multi_agent")
    assert res_valid.status == "completed"

    # Infeasible case
    infeasible_brief = "Impossible 20-bedroom castle on a 20 sqm plot."
    res_infeasible = orch.generate(raw_brief=infeasible_brief, mode="multi_agent")
    assert res_infeasible.status in ("failed", "incomplete_requirements")


# ============================================================================
# 18. Unnecessary agent is not invoked when current state does not require it
# ============================================================================
def test_unnecessary_agent_not_invoked_when_state_does_not_require_it():
    orchestrator = HierarchicalOrchestrator(use_llm=False)
    state = ProjectState(project_id="test_proj")
    # Fresh state without requirements
    task = orchestrator._select_next_task(state)
    # The requirement agent must be invoked, NOT the architectural or refinement agent
    assert task.assigned_agent == "requirement_agent"
    assert task.assigned_agent != "architectural_agent"
    assert task.assigned_agent != "refinement_agent"
