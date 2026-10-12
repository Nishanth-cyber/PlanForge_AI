"""Regression test for case_16_infeasible_deficit comparing pipeline and agentic modes."""

from __future__ import annotations

import pytest

from app.evaluation.benchmark import BenchmarkRegistry
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator


def test_case_16_infeasible_deficit_comparison():
    """Verify that agentic mode handles the severe deficit with structured evidence while pipeline mode preserves baseline."""
    case = BenchmarkRegistry.get_case("case_16_infeasible_deficit")
    assert case is not None

    orch = PlanForgeOrchestrator()

    # 1. Pipeline Mode Baseline Execution
    cfg_pipe = OrchestrationConfig(mode="pipeline")
    res_pipe = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_pipe)

    assert res_pipe.status == "failed"
    assert res_pipe.is_success is False
    assert res_pipe.is_valid is False
    assert res_pipe.floor_plan_set is None
    assert "deficit" in (res_pipe.error_message or "").lower()

    # 2. Agentic Mode Execution
    cfg_agent = OrchestrationConfig(mode="agentic")
    res_agent = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_agent)

    # Verifications mandated by Section 6:
    # A. InfeasibleAllocationError caught and handled gracefully
    assert res_agent.status == "failed"
    assert res_agent.is_success is False
    assert res_agent.is_valid is False
    assert res_agent.floor_plan_set is None

    # B. Preserves the measured area deficit and relevant evidence
    assert res_agent.error_message is not None
    assert "deficit of 118.2" in res_agent.error_message or "exceeds" in res_agent.error_message

    # C. Produces structured infeasibility outcome in agentic state
    assert res_agent.agentic_state is not None
    infeas_ev = res_agent.agentic_state.get("infeasibility_evidence", [])
    assert len(infeas_ev) > 0
    assert any("deficit" in str(ev) or "infeasible" in str(ev) for ev in infeas_ev)

    # D. Decisions and tool calls recorded cleanly
    assert len(res_agent.decisions) > 0
    tools = [tc["tool"] for tc in res_agent.agentic_state.get("tool_calls", [])]
    assert "parse_requirements" in tools
