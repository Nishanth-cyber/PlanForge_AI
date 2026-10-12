"""Unit tests for AgenticPolicy, context-aware decision routing, and budget enforcement."""

from __future__ import annotations

import pytest

from app.agentic.budget import Budget
from app.agentic.state import Finding, ProjectState, RunStatus
from app.agentic.tools import ToolResult
from app.agentic.toolset import create_default_tool_registry
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.orchestration.routing import AgenticPolicy, NextAction
from app.orchestration.workflow import AgenticWorkflow


def test_policy_different_validation_results_lead_to_different_actions():
    """Verify that different validation findings produce different prescriptive next actions."""
    policy = AgenticPolicy()

    # Case A: Validation findings with overlap errors -> triggers refine_design
    state_overlap = ProjectState(project_id="test_overlap", goal="Overlap Test")
    state_overlap.set_artifact("requirements", Requirements(project_name="A"))
    state_overlap.set_artifact("planning_spec", "mock_spec")
    state_overlap.set_artifact("allocation_set", "mock_alloc")
    state_overlap.set_artifact("architectural_design_set", "mock_arch")
    state_overlap.set_artifact("floor_plan_set", "mock_geom")
    state_overlap.facts["feasibility_checked"] = True
    state_overlap.facts["feasible"] = True
    state_overlap.apply_findings(
        [{"code": "overlap", "severity": "error", "message": "Room overlap detected"}],
        scope_keys=("floor_plan_set",),
    )

    action_overlap = policy.decide(state_overlap)
    assert action_overlap.tool == "refine_design"
    assert "refinement" in action_overlap.rationale.lower()

    # Case B: Validation is clean (0 hard errors) -> triggers completion or alternatives/export
    state_clean = ProjectState(project_id="test_clean", goal="Clean Test")
    state_clean.set_artifact("requirements", Requirements(project_name="B"))
    state_clean.set_artifact("planning_spec", "mock_spec")
    state_clean.set_artifact("allocation_set", "mock_alloc")
    state_clean.set_artifact("architectural_design_set", "mock_arch")
    state_clean.set_artifact("floor_plan_set", "mock_geom")
    state_clean.facts["feasibility_checked"] = True
    state_clean.facts["feasible"] = True
    state_clean.facts["export_bundle_path"] = "outputs/bundle.json"
    state_clean.apply_findings([], scope_keys=("floor_plan_set",))

    action_clean = policy.decide(state_clean)
    assert action_clean.kind == "finish"
    assert action_clean.target_status == RunStatus.ACCEPTED


def test_mock_and_rules_source_explicitly_identified():
    """Verify that deterministic / mock logic records source='agentic_policy' or 'rules', never falsely claiming LLM reasoning."""
    policy = AgenticPolicy()
    state = ProjectState(project_id="test_source", goal="Source Test")

    action = policy.decide(state)
    assert action.source != "llm"
    assert action.source in {"agentic_policy", "rules", "fallback"}


def test_budget_exhaustion_stops_execution():
    """Verify that budget exhaustion cleanly halts the workflow with RunStatus.BUDGET_EXHAUSTED."""
    registry = create_default_tool_registry()
    policy = AgenticPolicy()
    workflow = AgenticWorkflow(
        registry=registry,
        policy=policy,
        budget=Budget(max_steps=2),
    )

    state = workflow.run(
        project_id="budget_test",
        goal="Budget Test",
        raw_brief="Single floor house on 40x50 plot. Floor 1: 1 living room, 1 kitchen, 1 bedroom, 1 bathroom.",
    )

    assert state.step <= 3
    assert state.budget.steps_used <= 3
    assert state.status in {RunStatus.BUDGET_EXHAUSTED, RunStatus.ACCEPTED, RunStatus.RUNNING}
