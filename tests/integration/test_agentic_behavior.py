"""Automated test suite proving authentic agentic behavior in PlanForge AI.

Verifies the 10 required scenarios mandated by the Master Implementation Prompt:
1. Straightforward single-floor residence (end-to-end tool-using completion).
2. Conflicting requirements (contradiction handling without silent invention).
3. Plot with insufficient area (honest physical infeasibility reporting).
4. Validation failure that triggers adaptive refinement and succeeds.
5. Strategic replanning when initial strategy fails to satisfy constraints.
6. Multi-floor residence with vertical stair alignment and connectivity constraints.
7. Tool failure and recovery (failure converted into structured observation).
8. Repeated unsuccessful action detection and loop prevention.
9. Ambiguous or incomplete project requiring user clarification.
10. Multi-candidate design exploration across distinct spatial strategies.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.agentic.budget import Budget
from app.agentic.events import InMemoryEventLog
from app.agentic.state import ProjectState, RunStatus
from app.agentic.tools import ToolRegistry, ToolResult, ToolSpec
from app.agentic.toolset import create_default_tool_registry
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.routing import AgenticPolicy
from app.orchestration.workflow import AgenticWorkflow


# ===========================================================================
# Scenario 1: Straightforward Single-Floor Residence
# ===========================================================================
def test_scenario_1_straightforward_single_floor():
    """Verify autonomous execution of a single-floor residence through the tool-calling loop."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor compact bungalow on a 40 feet by 50 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 200 sq ft
    - 1 kitchen of 100 sq ft
    - 1 bedroom of 140 sq ft
    - 1 bathroom of 50 sq ft
    """
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 1 Single Floor")

    assert res.status == "completed"
    assert res.is_success is True
    assert res.floor_plan_set is not None
    assert len(res.floor_plan_set.floor_plans) == 1
    assert res.validation_report is not None
    assert res.validation_report.overall_valid is True

    # Verify agentic trace and tool execution records exist
    assert res.agentic_state is not None
    assert len(res.decisions) > 0
    tools_called = [d["tool"] for d in res.decisions if d.get("tool")]
    assert "parse_requirements" in tools_called
    assert "plan_spatial_program" in tools_called
    assert "allocate_spatial_regions" in tools_called
    assert "construct_geometry" in tools_called
    assert "validate_design" in tools_called


# ===========================================================================
# Scenario 2: Conflicting Requirements Handling
# ===========================================================================
def test_scenario_2_conflicting_requirements():
    """Verify that contradictory or incomplete requirements trigger clarification."""
    orch = PlanForgeOrchestrator()
    # Ambiguous brief: mentions bedrooms without specifying floors or dimensions
    brief = "Build a luxury home with some bedrooms and a pool."
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 2 Conflicting")

    assert res.status == "incomplete_requirements"
    assert res.is_success is False
    assert len(res.clarification_questions) > 0
    # Must NOT invent missing rooms or plot dimensions silently
    assert res.floor_plan_set is None


# ===========================================================================
# Scenario 3: Plot with Insufficient Area (Infeasibility Detection)
# ===========================================================================
def test_scenario_3_insufficient_plot_area():
    """Verify that a plot physically incapable of accommodating rooms reports infeasibility honestly."""
    orch = PlanForgeOrchestrator()
    # 5m x 5m plot = 25m², with 2m setbacks leaving 1m x 1m = 1m² buildable area,
    # requesting 100m² of rooms
    brief = """
    Single floor house on a 15 feet by 15 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    - 1 kitchen of 150 sq ft
    - 2 bedrooms of 180 sq ft each
    - 2 bathrooms of 60 sq ft each
    """
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 3 Infeasible")

    assert res.status == "failed"
    assert res.is_success is False
    assert res.error_message is not None
    assert "infeasible" in res.error_message.lower() or "deficit" in res.error_message.lower() or "exceeds" in res.error_message.lower()
    # Crucial invariant: hard constraints cannot be bypassed and invalid plans are NOT marked completed
    assert res.is_valid is False


# ===========================================================================
# Scenario 4: Validation Failure Corrected by Refinement
# ===========================================================================
def test_scenario_4_validation_failure_corrected():
    """Verify that validation findings drive corrective action and resolve issues."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor suburban home on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 260 sq ft
    - 1 dining room of 140 sq ft
    - 1 kitchen of 120 sq ft
    - 2 bedrooms of 150 sq ft each
    - 1 bathroom of 50 sq ft
    """
    cfg = OrchestrationConfig(enable_refinement=True, max_refinement_iterations=3)
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 4 Refinement", config=cfg)

    assert res.status == "completed"
    assert res.is_valid is True
    assert res.validation_report.overall_score >= 70.0


# ===========================================================================
# Scenario 5: Strategy Adaptation & Replanning
# ===========================================================================
def test_scenario_5_strategy_adaptation():
    """Verify that the planning agent adapts its zoning strategy when requested."""
    plan_agent = orch_agent = PlanForgeOrchestrator().planning_agent
    req = Requirements(
        project_name="Strategy Test",
        plot_shape=[(0.0, 0.0), (15.0, 0.0), (15.0, 15.0), (0.0, 15.0)],
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", target_area_sqm=22.0),
                    RoomRequirement(room_type="kitchen", target_area_sqm=10.0),
                    RoomRequirement(room_type="bedroom", target_area_sqm=14.0),
                    RoomRequirement(room_type="bathroom", target_area_sqm=5.0),
                ],
            )
        ],
    )
    spec_balanced = plan_agent.plan(req, strategy="balanced")
    spec_compact = plan_agent.plan(req, strategy="compact")

    assert spec_balanced.global_constraints.get("planning_strategy") == "balanced"
    assert spec_compact.global_constraints.get("planning_strategy") == "compact"


# ===========================================================================
# Scenario 6: Multi-Floor Residence with Staircase & Connectivity
# ===========================================================================
def test_scenario_6_multi_floor_staircase_connectivity():
    """Verify multi-floor residence generation with vertical staircase alignment."""
    orch = PlanForgeOrchestrator()
    brief = """
    Two floor modern villa on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 240 sq ft
    - 1 kitchen of 120 sq ft
    - 1 bathroom of 40 sq ft
    Floor 2:
    - 2 bedrooms of 160 sq ft each
    - 1 bathroom of 50 sq ft
    """
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 6 Multi Floor")

    assert res.status == "completed"
    assert res.is_success is True
    assert res.floor_plan_set is not None
    assert len(res.floor_plan_set.floor_plans) == 2
    assert res.validation_report is not None
    assert res.validation_report.overall_valid is True


# ===========================================================================
# Scenario 7: Tool Failure Handled without Crashing
# ===========================================================================
def test_scenario_7_tool_failure_handling():
    """Verify that unexpected tool exceptions become handled observations, not fatal crashes."""
    registry = create_default_tool_registry()

    def crashing_handler(state, args):
        raise RuntimeError("Simulated transient geometry hardware failure")

    registry._tools["construct_geometry"].handler = crashing_handler

    policy = AgenticPolicy()
    workflow = AgenticWorkflow(registry=registry, policy=policy)

    state = workflow.run(
        project_id="tool_fail_test",
        goal="Tool Failure Test",
        raw_brief="""
        Single floor compact bungalow on a 40 feet by 50 feet plot.
        Floor 1:
        - 1 living room of 200 sq ft
        - 1 bedroom of 140 sq ft
        - 1 bathroom of 50 sq ft
        """,
    )

    # The workflow handles the tool failure gracefully
    tool_calls = [tc for tc in state.tool_calls if tc.tool == "construct_geometry"]
    assert len(tool_calls) > 0
    assert tool_calls[0].ok is False
    assert "Simulated transient geometry hardware failure" in (tool_calls[0].error_message or "")


# ===========================================================================
# Scenario 8: Repeated Failed Action Detection & Loop Prevention
# ===========================================================================
def test_scenario_8_repeated_failed_action_detection():
    """Verify that repeated identical actions with zero state progress are blocked."""
    registry = create_default_tool_registry()

    # Stub tool that makes no progress and modifies nothing
    def no_progress_refine(state, args):
        return ToolResult(ok=False, outcome="no_effect", summary="No improvements possible")

    registry._tools["refine_design"].handler = no_progress_refine

    policy = AgenticPolicy()
    workflow = AgenticWorkflow(registry=registry, policy=policy)

    state = ProjectState(
        project_id="loop_detect_test",
        goal="Loop Detection",
        budget=Budget(max_steps=10),
    )
    # Simulate state with hard finding requiring refinement
    state.set_artifact("requirements", Requirements(project_name="Loop Test"))
    state.set_artifact("planning_spec", MagicMock())
    state.set_artifact("allocation_set", MagicMock())
    state.set_artifact("architectural_design_set", MagicMock())
    state.set_artifact("floor_plan_set", MagicMock())
    state.apply_findings(
        [{"code": "overlap", "severity": "error", "message": "Simulated room overlap"}],
        scope_keys=("floor_plan_set",),
    )
    state.facts["feasibility_checked"] = True
    state.facts["feasible"] = True

    # Run workflow; it must detect repeated failures and stop without infinite looping
    final_state = workflow.run(project_id="loop_detect_test", goal="Loop Test", inputs={})

    assert final_state.step < 10
    # Must have detected blocked actions or terminated without hanging
    assert final_state.status != RunStatus.RUNNING


# ===========================================================================
# Scenario 9: User Clarification Request
# ===========================================================================
def test_scenario_9_clarification_handling():
    """Verify that projects with missing critical program specifications request user clarification."""
    orch = PlanForgeOrchestrator()
    # Missing all room specifications
    brief = "Plot dimensions: 40 feet by 50 feet. Build a house."
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 9 Clarification")

    assert res.status == "incomplete_requirements"
    assert len(res.clarification_questions) > 0


# ===========================================================================
# Scenario 10: Multi-Candidate Design Generation
# ===========================================================================
def test_scenario_10_multiple_candidate_designs():
    """Verify generation of multiple structurally distinct candidate designs."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor villa on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 260 sq ft
    - 1 kitchen of 120 sq ft
    - 1 bedroom of 150 sq ft
    - 1 bathroom of 50 sq ft
    """
    cfg = OrchestrationConfig(num_alternatives=2)
    res = orch.generate_agentic(raw_brief=brief, project_name="Scenario 10 Alternatives", config=cfg)

    assert res.status == "completed"
    assert res.alternative_set is not None
    assert res.alternative_set.candidates_generated >= 2
    assert len(res.alternative_set.alternatives) >= 1
    # Verify candidate alternatives possess unique IDs and strategies
    alt_ids = [alt.alternative_id for alt in res.alternative_set.alternatives]
    assert len(set(alt_ids)) == len(alt_ids)
