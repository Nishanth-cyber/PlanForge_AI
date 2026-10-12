"""Comprehensive test suite for Phase 4: LLM-Powered Agentic Decision-Making.

Verifies the 16 required behaviors:
1. Configured LLM is genuinely invoked during action selection.
2. Valid LLM response can select different allowed actions for different states.
3. Tool arguments are validated before execution.
4. Unknown actions are rejected.
5. Malformed responses are handled safely.
6. Provider timeouts activate bounded fallback behavior.
7. LLM-call budgets are enforced.
8. Repeated actions cannot create infinite loops.
9. Validation findings influence later action selection.
10. A previous failed action influences subsequent decisions.
11. Hard validation errors prevent successful completion.
12. Infeasible requirements produce structured outcomes.
13. Mock mode is explicitly identified.
14. Live provider configuration is correctly propagated when available.
15. API responses and event logs do not expose credentials.
16. Existing mode="pipeline" tests continue to pass.
"""

from __future__ import annotations

import json
import pytest

from app.agentic.budget import Budget
from app.agentic.events import InMemoryEventLog
from app.agentic.state import Finding, ProjectState, RunStatus
from app.agentic.toolset import create_default_tool_registry
from app.llm.client import HuggingFaceClient, HuggingFaceTimeoutError, MockLLMClient
from app.llm.configuration import LLMConfig
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.orchestration.config import OrchestrationConfig
from app.orchestration.llm_selector import ActionDecision, LLMActionSelector
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.routing import AgenticPolicy, NextAction
from app.orchestration.workflow import AgenticWorkflow


# ===========================================================================
# 1. Configured LLM is genuinely invoked
# ===========================================================================
def test_configured_llm_is_genuinely_invoked():
    """Verify that the configured LLM client is called during action selection and decision records provenance."""
    registry = create_default_tool_registry()
    mock_client = MockLLMClient(
        default_response=json.dumps({
            "action": "parse_requirements",
            "arguments": {},
            "reason_code": "initial_parse",
            "evidence": ["raw_brief"],
            "expected_outcome": "Parse user input",
            "completion_assessment": "in_progress",
        })
    )
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_invoked", goal="Test Invocation")
    action = selector.decide(state)

    assert mock_client.call_count == 1
    assert action.source == "llm"
    assert action.tool == "parse_requirements"
    assert action.reason_code == "initial_parse"
    assert "llm_decision_requested" in event_log.types()
    assert "llm_response_received" in event_log.types()


# ===========================================================================
# 2. Different states lead to different LLM-selected actions
# ===========================================================================
def test_valid_llm_response_selects_different_actions_for_different_states():
    """Verify that different project states receive different context and select different allowed actions."""
    registry = create_default_tool_registry()

    # Call A: State needs spatial planning
    state_a = ProjectState(project_id="state_a", goal="Plan Test")
    state_a.set_artifact("requirements", Requirements(project_name="A"))
    state_a.facts["feasibility_checked"] = True
    state_a.facts["feasible"] = True

    resp_a = json.dumps({
        "action": "plan_spatial_program",
        "arguments": {"strategy": "balanced"},
        "reason_code": "plan_spatial",
        "evidence": ["feasibility_confirmed"],
        "expected_outcome": "Spatial program",
    })

    # Call B: State is fully validated and ready to export
    state_b = ProjectState(project_id="state_b", goal="Export Test")
    state_b.set_artifact("requirements", Requirements(project_name="B"))
    state_b.set_artifact("planning_spec", "mock_spec")
    state_b.set_artifact("allocation_set", "mock_alloc")
    state_b.set_artifact("architectural_design_set", "mock_arch")
    state_b.set_artifact("floor_plan_set", "mock_geom")
    state_b.facts["feasibility_checked"] = True
    state_b.facts["feasible"] = True
    state_b.apply_findings([], scope_keys=("floor_plan_set",))

    resp_b = json.dumps({
        "action": "export_bundle",
        "arguments": {"output_dir": "outputs"},
        "reason_code": "export_bundle",
        "evidence": ["valid_geometry"],
        "expected_outcome": "CAD DXF bundle",
    })

    client = MockLLMClient(responses=[resp_a, resp_b])
    selector = LLMActionSelector(registry=registry, llm_client=client)

    action_a = selector.decide(state_a)
    action_b = selector.decide(state_b)

    assert action_a.tool == "plan_spatial_program"
    assert action_b.tool == "export_bundle"
    assert action_a.tool != action_b.tool


# ===========================================================================
# 3. Tool arguments are validated before execution
# ===========================================================================
def test_tool_arguments_validated_before_execution():
    """Verify that invalid arguments (violating schema) are rejected and activate fallback."""
    registry = create_default_tool_registry()
    # allocate_spatial_regions expects integer seed, not invalid string or disallowed types
    mock_client = MockLLMClient(
        default_response=json.dumps({
            "action": "allocate_spatial_regions",
            "arguments": {"seed": "not_an_int", "invalid_param": 999},
            "reason_code": "bad_args",
        })
    )
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_val_args", goal="Arg Test")
    state.set_artifact("requirements", Requirements(project_name="Args"))
    state.set_artifact("planning_spec", "mock_spec")
    state.facts["feasibility_checked"] = True
    state.facts["feasible"] = True

    action = selector.decide(state)

    # Should reject the malformed proposal and fall back to the safe deterministic policy
    assert action.source == "fallback"
    assert "decision_rejected" in event_log.types()
    assert "fallback_activated" in event_log.types()
    assert action.tool == "allocate_spatial_regions"
    assert isinstance(action.args.get("seed"), int)  # Fallback provided valid integer seed


# ===========================================================================
# 4. Unknown actions are rejected
# ===========================================================================
def test_unknown_actions_rejected():
    """Verify that hallucinated / unauthorized tool names are rejected and trigger fallback."""
    registry = create_default_tool_registry()
    mock_client = MockLLMClient(
        default_response=json.dumps({
            "action": "hallucinated_room_synthesizer",
            "arguments": {"room": "penthouse"},
            "reason_code": "invent_room",
        })
    )
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_unknown", goal="Unknown Tool Test")
    action = selector.decide(state)

    assert action.source == "fallback"
    assert "Unknown tool 'hallucinated_room_synthesizer'" in (action.fallback_reason or "")
    assert "decision_rejected" in event_log.types()


# ===========================================================================
# 5. Malformed responses handled safely
# ===========================================================================
def test_malformed_responses_handled_safely():
    """Verify that non-JSON or garbled LLM responses do not crash the engine and activate fallback."""
    registry = create_default_tool_registry()
    mock_client = MockLLMClient(default_response="I think you should build a 3-bedroom house without walls.")
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_malformed", goal="Malformed Test")
    action = selector.decide(state)

    assert action.source == "fallback"
    assert "Malformed JSON" in (action.fallback_reason or "")
    assert "llm_decision_failed" in event_log.types()
    assert "fallback_activated" in event_log.types()


# ===========================================================================
# 6. Provider timeouts activate bounded fallback behavior
# ===========================================================================
def test_provider_timeouts_activate_bounded_fallback():
    """Verify that provider timeouts gracefully fall back to deterministic policy with honest logging."""
    registry = create_default_tool_registry()

    def timeout_generator(prompt: str, system: str | None = None) -> str:
        raise HuggingFaceTimeoutError("Request timed out after 60s")

    mock_client = MockLLMClient(generator=timeout_generator)
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_timeout", goal="Timeout Test")
    action = selector.decide(state)

    assert action.source == "fallback"
    assert "HuggingFaceTimeoutError" in (action.fallback_reason or "")
    assert "llm_decision_failed" in event_log.types()
    assert "fallback_activated" in event_log.types()


# ===========================================================================
# 7. LLM-call budgets are enforced
# ===========================================================================
def test_llm_call_budgets_enforced():
    """Verify that when the LLM-call budget is reached, fallback policy operates without calling the LLM."""
    registry = create_default_tool_registry()
    mock_client = MockLLMClient(default_response=json.dumps({"action": "check_feasibility", "arguments": {}}))
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(
        project_id="test_budget",
        goal="Budget Test",
        budget=Budget(max_llm_calls=1, llm_calls_used=1),  # Already exhausted
    )

    action = selector.decide(state)

    # Must NOT call client, must use rules or fallback immediately
    assert mock_client.call_count == 0
    assert action.source in {"fallback", "rules"}
    assert "budget exhausted" in (action.rationale or action.fallback_reason or "").lower()


# ===========================================================================
# 8. Repeated actions cannot create infinite loops
# ===========================================================================
def test_repeated_actions_cannot_create_infinite_loops():
    """Verify that repeated unproductive actions are detected, blocked, and trigger fallback."""
    registry = create_default_tool_registry()
    # LLM always insists on calling the exact same action
    mock_client = MockLLMClient(
        default_response=json.dumps({"action": "check_feasibility", "arguments": {}})
    )
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_anti_loop", goal="Loop Test")
    state.set_artifact("requirements", Requirements(project_name="Loop"))
    current_fp = state.fingerprint()
    action_key = "check_feasibility:[]"

    # Pre-simulate 3 failed attempts marking it blocked
    state.executed[action_key] = {
        "action_key": action_key,
        "tool": "check_feasibility",
        "args": {},
        "fingerprint": current_fp,
        "attempts": 3,
        "blocked": True,
    }

    action = selector.decide(state)

    # Should reject the blocked action and activate fallback
    assert action.source == "fallback"
    assert "blocked" in (action.fallback_reason or "").lower()


# ===========================================================================
# 9. Validation findings influence later action selection
# ===========================================================================
def test_validation_findings_influence_later_action_selection():
    """Verify that hard validation findings prompt targeted refinement action."""
    registry = create_default_tool_registry()

    state = ProjectState(project_id="test_findings", goal="Findings Test")
    state.set_artifact("requirements", Requirements(project_name="Findings"))
    state.set_artifact("planning_spec", "mock_spec")
    state.set_artifact("allocation_set", "mock_alloc")
    state.set_artifact("architectural_design_set", "mock_arch")
    state.set_artifact("floor_plan_set", "mock_geom")
    state.facts["feasibility_checked"] = True
    state.facts["feasible"] = True
    state.apply_findings(
        [{"code": "overlap", "severity": "error", "message": "Living room overlaps kitchen"}],
        scope_keys=("floor_plan_set",),
    )

    # Using the state-aware default mock generator
    selector = LLMActionSelector(registry=registry)
    action = selector.decide(state)

    assert action.tool == "refine_design"
    assert action.source == "llm"
    assert "refinement" in (action.reason_code or "").lower()


# ===========================================================================
# 10. A previous failed action influences subsequent decisions
# ===========================================================================
def test_previous_failed_action_influences_subsequent_decisions():
    """Verify that when refinement is blocked after repeated attempts, the selector replans strategy."""
    registry = create_default_tool_registry()

    state = ProjectState(project_id="test_replan", goal="Replan Test")
    state.set_artifact("requirements", Requirements(project_name="Replan"))
    state.set_artifact("planning_spec", "mock_spec")
    state.set_artifact("allocation_set", "mock_alloc")
    state.set_artifact("architectural_design_set", "mock_arch")
    state.set_artifact("floor_plan_set", "mock_geom")
    state.facts["feasibility_checked"] = True
    state.facts["feasible"] = True
    state.apply_findings(
        [{"code": "boundary_exceeded", "severity": "error", "message": "Room exceeds plot boundary"}],
        scope_keys=("floor_plan_set",),
    )

    # Simulate refinement blocked
    state.executed["refine_design:[('action', 'full_loop'), ('max_iterations', 2)]"] = {
        "action_key": "refine_design:[('action', 'full_loop'), ('max_iterations', 2)]",
        "tool": "refine_design",
        "args": {"action": "full_loop", "max_iterations": 2},
        "fingerprint": state.fingerprint(),
        "attempts": 3,
        "blocked": True,
    }

    selector = LLMActionSelector(registry=registry)
    action = selector.decide(state)

    # The selector detects refinement blockage and switches to replanning
    assert action.tool == "plan_spatial_program"
    assert action.args.get("strategy") == "compact"


# ===========================================================================
# 11. Hard validation errors prevent successful completion
# ===========================================================================
def test_hard_validation_errors_prevent_successful_completion():
    """Verify that if LLM attempts to 'finish' while hard errors remain, it is rejected."""
    registry = create_default_tool_registry()
    # LLM erroneously attempts to declare finish
    mock_client = MockLLMClient(
        default_response=json.dumps({"action": "finish", "arguments": {}, "reason_code": "premature_finish"})
    )
    event_log = InMemoryEventLog()
    selector = LLMActionSelector(registry=registry, llm_client=mock_client, event_log=event_log)

    state = ProjectState(project_id="test_premature", goal="Premature Finish Test")
    state.set_artifact("floor_plan_set", "mock_geom")
    state.apply_findings(
        [{"code": "unresolved_overlap", "severity": "error", "message": "Hard overlap remains"}],
        scope_keys=("floor_plan_set",),
    )

    action = selector.decide(state)

    # Premature finish rejected, fallback activates to resolve error
    assert action.kind != "finish"
    assert action.source == "fallback"
    assert "Hard validation errors" in (action.fallback_reason or "")
    assert "decision_rejected" in event_log.types()


# ===========================================================================
# 12. Infeasible requirements produce structured outcomes
# ===========================================================================
def test_infeasible_requirements_produce_structured_outcomes():
    """Verify that physical infeasibility produces structured terminal outcome."""
    registry = create_default_tool_registry()
    mock_client = MockLLMClient(
        default_response=json.dumps({
            "action": "declare_infeasible",
            "arguments": {"reason": "Total required room area exceeds plot buildable area by 118 m²."},
            "reason_code": "area_deficit_infeasible",
            "evidence": ["area_deficit"],
            "expected_outcome": "Clean infeasibility declaration",
            "completion_assessment": "infeasible",
        })
    )
    selector = LLMActionSelector(registry=registry, llm_client=mock_client)

    state = ProjectState(project_id="test_infeas", goal="Infeasible Test")
    action = selector.decide(state)

    assert action.kind == "finish"
    assert action.target_status == RunStatus.INFEASIBLE
    assert action.source == "llm"
    assert "deficit" in action.rationale.lower() or "exceeds" in action.rationale.lower()


# ===========================================================================
# 13. Mock mode is explicitly identified
# ===========================================================================
def test_mock_mode_explicitly_identified():
    """Verify that provider mode is reported as 'mock' when using mock client."""
    registry = create_default_tool_registry()
    selector = LLMActionSelector(registry=registry)

    assert selector.provider_mode == "mock"
    event_log = selector.event_log
    state = ProjectState(project_id="test_mode", goal="Mode Test")
    selector.decide(state)

    req_events = [e for e in event_log.all() if e.type == "llm_decision_requested"]
    assert len(req_events) > 0
    assert req_events[0].data.get("mode") == "mock"


# ===========================================================================
# 14. Live provider configuration is correctly propagated
# ===========================================================================
def test_live_provider_configuration_propagation():
    """Verify that live HuggingFace configuration propagates endpoint and timeout settings."""
    cfg = LLMConfig(
        provider="huggingface",
        model_name="custom/qwen-7b",
        timeout_seconds=45.0,
        api_base_url="https://api-inference.huggingface.co/models",
    )
    registry = create_default_tool_registry()
    selector = LLMActionSelector(registry=registry, config=cfg)

    assert selector.provider_mode == "live"
    assert isinstance(selector.client, HuggingFaceClient)
    assert selector.client.config.model_name == "custom/qwen-7b"
    assert selector.client.config.timeout_seconds == 45.0


# ===========================================================================
# 15. API responses and event logs do not expose credentials
# ===========================================================================
def test_api_and_event_logs_do_not_expose_credentials():
    """Verify that secret API tokens are NEVER logged in events or serialized state."""
    secret_token = "hf_SUPER_SECRET_TOKEN_XYZ_12345"
    cfg = LLMConfig(
        provider="mock",
        model_name="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        api_key=secret_token,
    )
    orch = PlanForgeOrchestrator()
    res = orch.generate_agentic(
        raw_brief="Single floor bungalow on 40x50 plot with 1 living, 1 kitchen, 1 bedroom, 1 bathroom.",
        project_name="Security Secret Test",
        config=OrchestrationConfig(llm_config=cfg),
    )

    # Check serialized result and agentic state
    state_json = json.dumps(res.agentic_state or {})
    decisions_json = json.dumps(res.decisions or [])

    assert secret_token not in state_json
    assert secret_token not in decisions_json
    assert secret_token not in (res.error_message or "")


# ===========================================================================
# 16. Existing mode="pipeline" tests continue to pass
# ===========================================================================
def test_existing_pipeline_mode_unaffected():
    """Verify that mode='pipeline' executes the original deterministic pipeline without calling the LLM action selector."""
    orch = PlanForgeOrchestrator()
    res = orch.generate(
        raw_brief="Single floor cottage on 40x50 plot with 1 living, 1 kitchen, 1 bed, 1 bath.",
        project_name="Pipeline Regression Check",
        config=OrchestrationConfig(mode="pipeline"),
    )

    assert res.status == "completed"
    assert res.is_success is True
    assert res.floor_plan_set is not None
    # Pipeline mode should not have agentic state
    assert res.agentic_state is None
