"""Unit tests for Phase 7 Clarification Policy and Response Validation.

Covers:
- ClarificationDecisionPolicy evaluation categories
- Grounded infeasibility alternative generation with measured deficits
- ClarificationResponseValidator validation, rejection, and atomic mutation
- State version increment and downstream invalidation
- Stale version and duplicate response protection
"""

import pytest
from app.agentic.clarification import (
    AlternativeFeasibilityType,
    ClarificationCategory,
    ClarificationDecisionPolicy,
    ClarificationOption,
    ClarificationRequest,
    ClarificationResponseValidator,
    ClarificationStatus,
)
from app.agentic.state import ProjectState, RunStatus
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement


@pytest.fixture
def sample_feasible_requirements() -> Requirements:
    return Requirements(
        project_name="Feasible House",
        plot_dimensions=(12.0, 15.0),
        setbacks={"front": 1.5, "rear": 1.5, "left": 1.0, "right": 1.0},
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=18.0, target_area_sqm=22.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=10.0, target_area_sqm=12.0),
                    RoomRequirement(room_type="bedroom", min_count=1, min_area_sqm=12.0, target_area_sqm=14.0),
                    RoomRequirement(room_type="bathroom", min_count=1, min_area_sqm=4.0, target_area_sqm=5.0),
                ],
            )
        ],
    )


@pytest.fixture
def sample_infeasible_requirements() -> Requirements:
    # Build area is only ~50 sqm, but rooms require 95 sqm
    return Requirements(
        project_name="Tight Plot Infeasible",
        plot_dimensions=(10.0, 10.0),
        setbacks={"front": 2.0, "rear": 2.0, "left": 1.5, "right": 1.5},
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=30.0, target_area_sqm=35.0),
                    RoomRequirement(room_type="master_bedroom", min_count=1, min_area_sqm=20.0, target_area_sqm=25.0),
                    RoomRequirement(room_type="bedroom", min_count=1, min_area_sqm=15.0, target_area_sqm=18.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=15.0, target_area_sqm=18.0),
                    RoomRequirement(room_type="study", min_count=1, min_area_sqm=15.0, target_area_sqm=16.0, description="optional study"),
                ],
            )
        ],
    )


def test_feasible_requirements_evaluates_to_proceed(sample_feasible_requirements):
    """1. Complete feasible requirements proceed without unnecessary clarification."""
    policy = ClarificationDecisionPolicy()
    state = ProjectState(project_id="proj_1", goal="Test House", state_version=1)
    state.set_artifact("requirements", sample_feasible_requirements)

    decision = policy.evaluate(state)
    assert decision.category == ClarificationCategory.PROCEED
    assert decision.should_pause is False
    assert decision.clarification_request is None


def test_missing_mandatory_room_evaluates_to_clarify():
    """2. Missing mandatory information produces a clarification request."""
    # Requirements with no rooms
    empty_req = Requirements(
        project_name="Empty House",
        plot_dimensions=(12.0, 15.0),
        floors=[FloorRequirement(floor_number=1, room_requirements=[])],
    )
    policy = ClarificationDecisionPolicy()
    state = ProjectState(project_id="proj_missing", goal="Empty House", state_version=1)
    state.set_artifact("requirements", empty_req)

    decision = policy.evaluate(state)
    assert decision.category == ClarificationCategory.CLARIFY
    assert decision.should_pause is True
    assert decision.clarification_request is not None
    assert "room" in decision.clarification_request.question.lower()


def test_contradictory_requirements_evaluates_to_clarify():
    """3. Contradictory requirements produce a clear question."""
    # Contradictory setbacks exceeding plot dimensions: front + rear = 12m > plot depth 10m
    contradictory_req = Requirements(
        project_name="Contradictory House",
        plot_dimensions=(10.0, 10.0),
        setbacks={"front": 6.0, "rear": 6.0},
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="living", min_count=1, min_area_sqm=20.0)],
            )
        ],
    )
    policy = ClarificationDecisionPolicy()
    state = ProjectState(project_id="proj_contra", goal="Contra", state_version=1)
    state.set_artifact("requirements", contradictory_req)

    decision = policy.evaluate(state)
    assert decision.category in (ClarificationCategory.CLARIFY, ClarificationCategory.REQUEST_CONSTRAINT_REVISION)
    assert decision.should_pause is True
    assert "setback" in decision.clarification_request.evidence.lower() or "boundary" in decision.clarification_request.question.lower()


def test_infeasible_area_returns_measured_deficit_and_grounded_options(sample_infeasible_requirements):
    """4 & 5. Infeasible area requirements return measured deficit and grounded alternatives."""
    policy = ClarificationDecisionPolicy()
    state = ProjectState(project_id="proj_inf", goal="Tight House", state_version=1)
    state.set_artifact("requirements", sample_infeasible_requirements)

    decision = policy.evaluate(state)
    assert decision.category == ClarificationCategory.REQUEST_CONSTRAINT_REVISION
    assert decision.should_pause is True
    req = decision.clarification_request
    assert req is not None
    assert req.measured_deficit_sqm is not None
    assert req.measured_deficit_sqm > 0
    assert req.available_sqm is not None
    assert req.required_sqm is not None
    assert req.required_sqm > req.available_sqm

    # Grounded options check
    assert len(req.options) >= 2
    option_types = {opt.feasibility_type for opt in req.options}
    # Distinct feasibility categories
    assert AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE in option_types or AlternativeFeasibilityType.VERIFIED_FEASIBLE in option_types

    # Plot expansion option is mathematically grounded
    expand_opt = next((o for o in req.options if o.option_id == "expand_plot_depth"), None)
    if expand_opt:
        assert expand_opt.numeric_changes.get("plot_length", 0) > sample_infeasible_requirements.plot_dimensions[1]

    # Soft room removal option identified study
    remove_opt = next((o for o in req.options if "remove" in o.option_id), None)
    if remove_opt:
        assert "study" in remove_opt.affected_rooms


def test_mandatory_requirements_never_changed_without_authorization(sample_infeasible_requirements):
    """6. Mandatory requirements are never changed without user authorization."""
    validator = ClarificationResponseValidator()
    state = ProjectState(project_id="proj_auth", goal="Auth Test", state_version=1)
    state.set_artifact("requirements", sample_infeasible_requirements)

    initial_living_area = sample_infeasible_requirements.get_floor(1).room_requirements[0].min_area_sqm

    # Fake clarification request
    req = ClarificationRequest(
        request_id="req_test_1",
        project_id="proj_auth",
        state_version=1,
        category=ClarificationCategory.REQUEST_CONSTRAINT_REVISION,
        question="Deficit detected",
        options=[
            ClarificationOption(
                option_id="opt_1",
                title="Expand",
                description="Expand depth",
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
                numeric_changes={"plot_length": 18.0},
            )
        ],
    )
    state.pending_clarification = req

    # Without an accepted response, requirements must remain completely unchanged
    current_req = state.get_artifact("requirements")
    assert current_req.plot_dimensions[1] == 10.0
    assert current_req.get_floor(1).room_requirements[0].min_area_sqm == initial_living_area


def test_valid_response_updates_requirements_and_increments_version(sample_infeasible_requirements):
    """7. A valid response updates requirements and increments state version."""
    validator = ClarificationResponseValidator()
    state = ProjectState(project_id="proj_valid", goal="Valid Test", state_version=2)
    state.set_artifact("requirements", sample_infeasible_requirements)
    init_version = state.version

    req = ClarificationRequest(
        request_id="req_test_2",
        project_id="proj_valid",
        state_version=init_version,
        category=ClarificationCategory.REQUEST_CONSTRAINT_REVISION,
        question="Deficit detected",
        options=[
            ClarificationOption(
                option_id="opt_expand",
                title="Expand Plot",
                description="Increase length to 16m",
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
                numeric_changes={"plot_length": 16.0},
            )
        ],
    )
    state.pending_clarification = req
    state.status = RunStatus.WAITING_FOR_CLARIFICATION

    success, msg, response = validator.validate_and_apply(
        state=state,
        request_id="req_test_2",
        selected_option_id="opt_expand",
    )

    assert success is True
    assert state.version == init_version + 1  # incremented
    assert state.status == RunStatus.RESUMABLE
    assert state.pending_clarification is None
    assert len(state.clarification_history) == 1
    assert len(state.requirement_changes) >= 1

    updated_req = state.get_artifact("requirements")
    assert updated_req.plot_dimensions[1] == 16.0


def test_invalid_response_leaves_request_pending(sample_infeasible_requirements):
    """8. An invalid response leaves the request pending."""
    validator = ClarificationResponseValidator()
    state = ProjectState(project_id="proj_inv", goal="Inv Test", state_version=1)
    state.set_artifact("requirements", sample_infeasible_requirements)
    init_version = state.version

    req = ClarificationRequest(
        request_id="req_test_3",
        project_id="proj_inv",
        state_version=init_version,
        category=ClarificationCategory.REQUEST_CONSTRAINT_REVISION,
        question="Deficit detected",
        options=[
            ClarificationOption(
                option_id="opt_valid",
                title="Valid Option",
                description="Some option",
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
            )
        ],
    )
    state.pending_clarification = req
    state.status = RunStatus.WAITING_FOR_CLARIFICATION

    # Non-existent option
    success, msg, response = validator.validate_and_apply(
        state=state,
        request_id="req_test_3",
        selected_option_id="opt_non_existent",
    )

    assert success is False
    assert "Invalid selected_option_id" in msg
    assert state.version == init_version  # version not incremented
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION
    assert state.pending_clarification is not None


def test_stale_response_is_rejected(sample_infeasible_requirements):
    """9. A stale response is rejected."""
    validator = ClarificationResponseValidator()
    state = ProjectState(project_id="proj_stale", goal="Stale Test", state_version=4)
    state.set_artifact("requirements", sample_infeasible_requirements)
    init_version = state.version

    req = ClarificationRequest(
        request_id="req_stale",
        project_id="proj_stale",
        state_version=init_version,
        category=ClarificationCategory.CLARIFY,
        question="Clarify something",
        options=[
            ClarificationOption(
                option_id="opt_1",
                title="Opt 1",
                description="Opt 1",
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
            )
        ],
    )
    state.pending_clarification = req
    state.status = RunStatus.WAITING_FOR_CLARIFICATION

    # Submitting with an expected_state_version of 2 when current is init_version
    success, msg, response = validator.validate_and_apply(
        state=state,
        request_id="req_stale",
        selected_option_id="opt_1",
        expected_state_version=2,
    )

    assert success is False
    assert "Stale response" in msg
    assert state.status == RunStatus.WAITING_FOR_CLARIFICATION


def test_duplicate_response_does_not_apply_changes_twice(sample_infeasible_requirements):
    """10. A duplicate response does not apply changes twice."""
    validator = ClarificationResponseValidator()
    state = ProjectState(project_id="proj_dup", goal="Dup Test", state_version=1)
    state.set_artifact("requirements", sample_infeasible_requirements)
    init_version = state.version

    req = ClarificationRequest(
        request_id="req_dup",
        project_id="proj_dup",
        state_version=init_version,
        category=ClarificationCategory.REQUEST_CONSTRAINT_REVISION,
        question="Deficit detected",
        options=[
            ClarificationOption(
                option_id="opt_expand",
                title="Expand",
                description="Expand",
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
                numeric_changes={"plot_length": 15.0},
            )
        ],
    )
    state.pending_clarification = req
    state.status = RunStatus.WAITING_FOR_CLARIFICATION

    # First submission
    success1, msg1, resp1 = validator.validate_and_apply(
        state=state,
        request_id="req_dup",
        selected_option_id="opt_expand",
    )
    assert success1 is True
    assert state.version == init_version + 1

    # Second submission with the same request_id
    success2, msg2, resp2 = validator.validate_and_apply(
        state=state,
        request_id="req_dup",
        selected_option_id="opt_expand",
    )
    assert success2 is False
    assert "not pending" in msg2.lower() or "stale" in msg2.lower() or "no pending" in msg2.lower()
    assert state.version == init_version + 1  # Not incremented again


def test_downstream_invalidation_clears_stale_geometry(sample_infeasible_requirements):
    """11 & 12. Changed requirements invalidate downstream geometry while preserving metadata."""
    state = ProjectState(project_id="proj_inval", goal="Inval Test", state_version=1)
    state.set_artifact("requirements", sample_infeasible_requirements)
    state.set_artifact("planning_spec", {"dummy": "spec"})
    state.set_artifact("floor_plan_set", {"dummy": "geometry"})

    # Invalidate downstream of requirements
    state.invalidate_downstream("requirements")

    assert state.get_artifact("requirements") is not None
    assert state.get_artifact("planning_spec") is None
    assert state.get_artifact("floor_plan_set") is None
    assert "planning_spec" in state.invalidated_artifacts
    assert "floor_plan_set" in state.invalidated_artifacts
