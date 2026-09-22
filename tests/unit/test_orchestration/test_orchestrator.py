"""Unit tests for the PlanForge central orchestrator and pipeline coordination."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.geometry.engine import GeometryEngine
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import (
    PlanForgeOrchestrator,
    create_default_orchestrator,
)
from app.orchestration.pipeline import PipelineResult
from app.orchestration.state import StageName, StageStatus
from app.validation.validator import FloorPlanValidator


def test_orchestrator_initialization_and_injection():
    """Verify that PlanForgeOrchestrator accepts clean dependency injection."""
    req_agent = RequirementAgent()
    plan_agent = PlanningAgent()
    asaa = ASAAAllocator(seed=42)
    arch_agent = ArchitecturalAgent()
    geom_engine = GeometryEngine()
    validator = FloorPlanValidator()

    orch = PlanForgeOrchestrator(
        requirement_agent=req_agent,
        planning_agent=plan_agent,
        asaa_allocator=asaa,
        architectural_agent=arch_agent,
        geometry_engine=geom_engine,
        validator=validator,
    )

    assert orch.requirement_agent is req_agent
    assert orch.planning_agent is plan_agent
    assert orch.asaa_allocator is asaa
    assert orch.architectural_agent is arch_agent
    assert orch.geometry_engine is geom_engine
    assert orch.validator is validator

    # Default factory test
    default_orch = create_default_orchestrator()
    assert isinstance(default_orch, PlanForgeOrchestrator)


def test_pipeline_stage_ordering(tmp_path: Path):
    """Verify that all 10 pipeline stages execute in the authoritative order."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor cottage on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    - 1 kitchen of 150 sq ft
    """
    cfg = OrchestrationConfig(
        num_alternatives=1,
        enable_refinement=False,
        enable_rendering=True,
        enable_exports=True,
        output_dir=str(tmp_path / "outputs_order"),
    )

    res = orch.generate(raw_brief=brief, project_name="Ordering Test", config=cfg)

    assert res.status == "completed"
    assert res.is_success is True

    # Check stage records
    records = res.stage_records
    expected_stages = [
        "REQUIREMENT",
        "PLANNING",
        "ASAA",
        "ARCHITECTURAL_DESIGN",
        "GEOMETRY",
        "VALIDATION",
        "REFINEMENT",
        "MULTI_DESIGN",
        "EXPLAINABILITY",
        "EXPORT",
    ]
    for stg in expected_stages:
        assert stg in records, f"Stage {stg} missing from records"
        assert records[stg].status == StageStatus.COMPLETED


def test_incomplete_requirements_handling():
    """Verify that incomplete requirements stop the pipeline immediately.

    Planning, ASAA, Geometry, etc. must NOT be invoked.
    """
    mock_plan = MagicMock()
    mock_asaa = MagicMock()
    mock_geom = MagicMock()

    orch = PlanForgeOrchestrator(
        planning_agent=mock_plan,
        asaa_allocator=mock_asaa,
        geometry_engine=mock_geom,
    )

    # Incomplete brief missing plot dimensions entirely
    incomplete_brief = """
    House with:
    - 1 living room
    - 1 kitchen
    """
    res = orch.generate(raw_brief=incomplete_brief, project_name="Incomplete Test")

    assert res.status == "incomplete_requirements"
    assert res.is_success is False
    assert len(res.missing_fields) > 0

    # Downstream components must NOT have been called
    mock_plan.plan.assert_not_called()
    mock_asaa.allocate.assert_not_called()
    mock_geom.construct.assert_not_called()

    # Stage statuses
    assert res.stage_records["REQUIREMENT"].status == StageStatus.FAILED
    assert res.stage_records["PLANNING"].status == StageStatus.SKIPPED
    assert res.stage_records["ASAA"].status == StageStatus.SKIPPED
    assert res.stage_records["GEOMETRY"].status == StageStatus.SKIPPED


def test_stage_failure_and_downstream_skipping():
    """Verify that unrecoverable stage failure marks it FAILED and skips downstream stages."""
    failing_geom = MagicMock()
    failing_geom.construct.side_effect = RuntimeError("Geometric topology construction crashed")

    mock_val = MagicMock()

    orch = PlanForgeOrchestrator(
        geometry_engine=failing_geom,
        validator=mock_val,
    )

    brief = """
    Single floor home on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    """
    res = orch.generate(raw_brief=brief, project_name="Failure Test")

    assert res.status == "failed"
    assert res.is_success is False
    assert "Geometric topology construction crashed" in (res.error_message or "")

    # Geometry failed
    assert res.stage_records["GEOMETRY"].status == StageStatus.FAILED

    # Downstream skipped
    assert res.stage_records["VALIDATION"].status == StageStatus.SKIPPED
    assert res.stage_records["REFINEMENT"].status == StageStatus.SKIPPED
    assert res.stage_records["MULTI_DESIGN"].status == StageStatus.SKIPPED
    assert res.stage_records["EXPORT"].status == StageStatus.SKIPPED

    # Validator was never called
    mock_val.validate.assert_not_called()


def test_multi_design_diversity_coordination(tmp_path: Path):
    """Verify orchestrator generates multiple alternatives neutrally without best-design ranking."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor home on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 280 sq ft
    - 1 dining room of 140 sq ft
    - 1 kitchen of 120 sq ft
    """
    cfg = OrchestrationConfig(
        num_alternatives=2,
        candidate_budget=4,
        enable_rendering=True,
        enable_exports=True,
        output_dir=str(tmp_path / "outputs_multi"),
    )

    res = orch.generate(raw_brief=brief, project_name="Multi-Design Orch Test", config=cfg)

    assert res.status == "completed"
    assert res.alternative_set is not None
    assert len(res.alternative_set.alternatives) == 2

    alts = res.alternative_set.alternatives
    assert alts[0].alternative_id != alts[1].alternative_id
    assert alts[0].strategy != alts[1].strategy

    # Check that export dictionary and summary do NOT rank them as best/winner
    summary_dict = res.to_dict()
    alts_serialized = summary_dict["alternatives"]
    assert len(alts_serialized) == 2
    for a in alts_serialized:
        assert "is_best" not in a
        assert "rank" not in a
        assert "winner" not in a


def test_explainability_trace_aggregation():
    """Verify that DecisionTrace captures complete end-to-end stage events."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor home on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    - 1 kitchen of 150 sq ft
    """
    cfg = OrchestrationConfig(enable_exports=False)
    res = orch.generate(raw_brief=brief, project_name="Trace Orch Test", config=cfg)

    assert res.status == "completed"
    assert res.decision_trace is not None
    trace = res.decision_trace

    # Trace must have events across requirements, planning, allocation, design, geometry, validation
    stage_names = [s.stage_name for s in trace.stages]
    assert "requirement" in stage_names
    assert "planning" in stage_names
    assert "asaa_allocation" in stage_names
    assert "geometry" in stage_names
    assert "validation" in stage_names


def test_no_room_invention_on_missing_floors():
    """Verify that if Floor 2 is specified without rooms, the orchestrator does NOT invent them."""
    orch = PlanForgeOrchestrator()
    # User specifies 2 floors but only describes floor 1 rooms
    brief = """
    Two floor residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Target floors: 2
    Floor 1:
    - 1 living room of 300 sq ft
    """
    res = orch.generate(raw_brief=brief, project_name="No Invention Test")

    assert res.status == "incomplete_requirements"
    assert 2 in res.missing_floors
    assert res.planning_spec is None
    assert res.floor_plan_set is None
