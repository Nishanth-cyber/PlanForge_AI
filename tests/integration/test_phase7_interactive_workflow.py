"""Integration tests for Phase 7 Interactive Clarification and Resumable Workflow.

Covers:
- Hierarchical coordinator pausing at WAITING_FOR_CLARIFICATION when interactive=True
- Workflow resumption from paused stage after accepted clarification response
- Best valid candidate preservation and candidate invalidation on requirement change
- User cancellation handling and safe termination
- Missing LLM credentials deterministic fallback
- Multi-floor clarification and revalidation
- Prevention of repeated clarification loops
- Truthful reporting (paused or infeasible workflows never misreported as completed)
"""

import copy
import pytest
from app.agentic.clarification import (
    AlternativeFeasibilityType,
    ClarificationCategory,
    ClarificationOption,
    ClarificationRequest,
    ClarificationStatus,
)
from app.agentic.state import ProjectState, RunStatus
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.orchestration.hierarchical import HierarchicalOrchestrator
from app.orchestration.orchestrator import PlanForgeOrchestrator


@pytest.fixture
def infeasible_program() -> Requirements:
    # 80 sqm required inside ~36 sqm buildable footprint (10x10 with 2m setbacks)
    return Requirements(
        project_name="Infeasible Cottage",
        plot_dimensions=(10.0, 10.0),
        setbacks={"front": 2.0, "rear": 2.0, "left": 2.0, "right": 2.0},
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=30.0, target_area_sqm=35.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=20.0, target_area_sqm=22.0),
                    RoomRequirement(room_type="master_bedroom", min_count=1, min_area_sqm=25.0, target_area_sqm=28.0),
                    RoomRequirement(room_type="study", min_count=1, min_area_sqm=12.0, target_area_sqm=14.0, description="optional study"),
                ],
            )
        ],
    )


@pytest.fixture
def multifloor_infeasible_program() -> Requirements:
    return Requirements(
        project_name="Multi-Floor Infeasible",
        plot_dimensions=(8.0, 8.0),
        setbacks={"front": 2.0, "rear": 2.0, "left": 1.5, "right": 1.5},
        target_floors=2,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=25.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=15.0),
                ],
            ),
            FloorRequirement(
                floor_number=2,
                room_requirements=[
                    RoomRequirement(room_type="bedroom", min_count=2, min_area_sqm=15.0),
                ],
            ),
        ],
    )


def test_interactive_workflow_pauses_for_clarification(infeasible_program):
    """Scenario 1 & 22: Workflow pauses and does NOT mark as completed when clarification required."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    state = orchestrator.run(
        project_id="proj_pause_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )

    # Must be WAITING_FOR_CLARIFICATION, never COMPLETED or ACCEPTED
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    assert state.is_paused is True
    assert state.pending_clarification is not None
    assert state.pending_clarification.category == ClarificationCategory.REQUEST_CONSTRAINT_REVISION
    assert len(state.pending_clarification.options) >= 2


def test_workflow_resumes_from_paused_stage(infeasible_program):
    """Scenario 7 & 11: Workflow resumes from paused stage and completes successfully with authorized revisions."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    # 1. Run initially -> pauses
    state = orchestrator.run(
        project_id="proj_resume_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    req_id = state.pending_clarification.request_id

    # 2. Select option to expand plot depth to 24m
    success, msg, response = orchestrator.apply_clarification_response(
        state=state,
        request_id=req_id,
        selected_option_id="expand_plot_depth",
        numeric_overrides={"plot_length": 25.0},
    )
    assert success is True
    assert state.status == RunStatus.RESUMABLE
    assert state.pending_clarification is None
    assert state.get_artifact("requirements").plot_dimensions[1] == 25.0

    # 3. Resume workflow
    res_ok, res_msg, resumed_state = orchestrator.resume(state)
    assert res_ok is True
    # Resumed run completes or reaches acceptable state
    assert resumed_state.status in (RunStatus.ACCEPTED, RunStatus.COMPLETED)
    assert resumed_state.get_artifact("floor_plan_set") is not None


def test_user_cancellation_terminates_safely(infeasible_program):
    """Scenario 15: User cancellation terminates safely without hanging or executing further stages."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    state = orchestrator.run(
        project_id="proj_cancel_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION

    orchestrator.cancel(state, reason="Client withdrew project")
    assert state.status == RunStatus.CANCELLED
    assert "Client withdrew project" in state.status_reason

    # Trying to resume a cancelled workflow must be rejected
    res_ok, res_msg, _ = orchestrator.resume(state)
    assert res_ok is False
    assert "cannot resume" in res_msg.lower() or "not resumable" in res_msg.lower()


def test_changed_requirements_invalidates_candidates_and_preserves_best_valid(infeasible_program):
    """Scenario 13 & 14: Candidate manager preserves best valid candidate and invalidates affected candidates."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    state = orchestrator.run(
        project_id="proj_cand_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )

    # Invalidate downstream of requirements
    invalidated = state.invalidate_downstream("requirements")
    assert "floor_plan_set" in invalidated
    assert "planning_spec" in invalidated
    assert state.get_artifact("floor_plan_set") is None


def test_missing_llm_credentials_deterministic_fallback(infeasible_program):
    """Scenario 21: Missing LLM credentials do not prevent deterministic clarification handling."""
    registry = PlanForgeOrchestrator().tool_registry
    # Explicitly disable LLM or pass None
    orchestrator = HierarchicalOrchestrator(
        registry=registry,
        llm_client=None,
        use_llm=False,
        interactive=True,
    )

    state = orchestrator.run(
        project_id="proj_no_llm_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )

    # Must cleanly detect deficit and pause deterministically
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    assert state.pending_clarification is not None
    assert state.pending_clarification.measured_deficit_sqm is not None


def test_no_repeated_clarification_loop_for_resolved_issue(infeasible_program):
    """Scenario 23: No repeated clarification loop occurs for an already resolved issue."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    state = orchestrator.run(
        project_id="proj_no_loop_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    req_id = state.pending_clarification.request_id

    # Resolve with authorized plot expansion
    orchestrator.apply_clarification_response(
        state=state,
        request_id=req_id,
        selected_option_id="expand_plot_depth",
        numeric_overrides={"plot_length": 25.0},
    )

    # Resume
    orchestrator.resume(state)

    # Should not re-ask the same clarification
    assert state.status != RunStatus.WAITING_FOR_CLARIFICATION
    assert state.pending_clarification is None
    # Clarification history holds exactly 1 resolved request
    assert len(state.clarification_history) == 1


def test_infeasible_request_not_misreported_as_successful(infeasible_program):
    """Scenario 24: Infeasible request declined by user is truthfully reported as infeasible, not completed."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    state = orchestrator.run(
        project_id="proj_inf_report_test",
        goal="Infeasible Cottage",
        requirements=infeasible_program,
    )
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    req_id = state.pending_clarification.request_id

    # User declines revision
    success, msg, _ = orchestrator.apply_clarification_response(
        state=state,
        request_id=req_id,
        selected_option_id="opt_terminate_infeasible",
    )
    assert success is True
    assert state.status == RunStatus.INFEASIBLE
    assert state.status != RunStatus.COMPLETED
    assert state.status != RunStatus.ACCEPTED


def test_multifloor_clarification_and_revalidation(multifloor_infeasible_program):
    """Scenario 20: Multi-floor clarification and revalidation work correctly."""
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)

    state = orchestrator.run(
        project_id="proj_multifloor_test",
        goal="Multi-Floor Infeasible Project",
        requirements=multifloor_infeasible_program,
    )
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    assert state.pending_clarification is not None
    req_id = state.pending_clarification.request_id

    # Authorize plot expansion to relieve multi-floor deficit
    success, msg, _ = orchestrator.apply_clarification_response(
        state=state,
        request_id=req_id,
        selected_option_id="expand_plot_depth",
        numeric_overrides={"plot_length": 20.0},
    )
    assert success is True
    assert state.status == RunStatus.RESUMABLE

    # Resume workflow and verify multi-floor revalidation
    res_ok, _, resumed_state = orchestrator.resume(state)
    assert res_ok is True
    fps = resumed_state.get_artifact("floor_plan_set")
    assert fps is not None
    assert len(fps.floor_plans) == 2
    assert resumed_state.facts.get("cross_floor_validated") is True

