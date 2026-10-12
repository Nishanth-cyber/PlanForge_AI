"""Deterministic Fault Injection Framework for PlanForge Robustness & Recovery Evaluation.

Provides controlled, testable fault injection mechanisms simulating:
1. LLM failures (timeout, connection failure, rate limits, malformed JSON, schema invalidity,
   repeated failures, missing credentials, budget exhaustion).
2. Tool & geometry failures (ASAA allocation exception, geometry exception, invalid polygon,
   missing artifact, door/connectivity exception, validation exception, export failure).
3. Orchestration failures (agent delegation failure, stale proposal versioning, cycle detection,
   cancellation, interruption at safe checkpoints, state restoration & resume, duplicate clarification).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generator, List, Optional
from unittest.mock import patch

from app.models.geometry import Geometry, GeoRoom, GeoWall
from app.models.requirements import Requirements
from app.agentic.budget import Budget
from app.orchestration.errors import OrchestrationError
from app.agentic.state import ProjectState, RunStatus


class FaultType(str, Enum):
    # LLM faults
    LLM_TIMEOUT = "llm_timeout"
    LLM_CONNECTION_ERROR = "llm_connection_error"
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_MALFORMED_OUTPUT = "llm_malformed_output"
    LLM_SCHEMA_INVALID = "llm_schema_invalid"
    LLM_REPEATED_INVALID = "llm_repeated_invalid"
    LLM_MISSING_CREDENTIALS = "llm_missing_credentials"
    LLM_BUDGET_EXHAUSTED = "llm_budget_exhausted"

    # Tool & geometry faults
    ASAA_ALLOCATION_EXCEPTION = "asaa_allocation_exception"
    GEOMETRY_CONSTRUCTION_EXCEPTION = "geometry_construction_exception"
    INVALID_POLYGON = "invalid_polygon"
    MISSING_GEOMETRY_ARTIFACT = "missing_geometry_artifact"
    DOOR_CONNECTIVITY_FAILURE = "door_connectivity_failure"
    VALIDATION_EXCEPTION = "validation_exception"
    EXPORT_FAILURE = "export_failure"

    # Orchestration faults
    AGENT_DELEGATION_FAILURE = "agent_delegation_failure"
    STALE_PROPOSAL = "stale_proposal"
    REPEATED_ACTION_CYCLE = "repeated_action_cycle"
    CANCELLATION = "cancellation"
    INTERRUPTION_CHECKPOINT = "interruption_checkpoint"
    STATE_RESTORE_RESUME = "state_restore_resume"
    CONCURRENT_CLARIFICATION = "concurrent_clarification"
    REQUIREMENT_MUTATION_FAILURE = "requirement_mutation_failure"


@dataclass
class FaultRecord:
    """Audit record of an injected fault and its system recovery response."""

    fault_type: FaultType
    target_component: str
    injected_at_step: int
    payload: Dict[str, Any] = field(default_factory=dict)
    exception_raised: Optional[str] = None
    recovered_successfully: bool = False
    fallback_invoked: bool = False
    preserved_best_valid: bool = False
    terminal_status: Optional[str] = None
    audit_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_type": self.fault_type.value,
            "target_component": self.target_component,
            "injected_at_step": self.injected_at_step,
            "payload": self.payload,
            "exception_raised": self.exception_raised,
            "recovered_successfully": self.recovered_successfully,
            "fallback_invoked": self.fallback_invoked,
            "preserved_best_valid": self.preserved_best_valid,
            "terminal_status": self.terminal_status,
            "audit_notes": self.audit_notes,
        }


class FaultInjector:
    """Controller for deterministic, reproducible fault injection during test & benchmark execution."""

    @staticmethod
    @contextlib.contextmanager
    def inject_llm_failure(
        fault_type: FaultType,
        client: Any,
        trigger_count: int = 1,
    ) -> Generator[Dict[str, Any], None, None]:
        """Inject specific LLM error into a LLM client instance."""
        calls = {"count": 0, "intercepted": False}
        original_generate = getattr(client, "generate", None)

        def faulty_generate(*args: Any, **kwargs: Any) -> Any:
            calls["count"] += 1
            if calls["count"] <= trigger_count:
                calls["intercepted"] = True
                if fault_type == FaultType.LLM_TIMEOUT:
                    raise TimeoutError("Simulated LLM provider timeout after 30.0s")
                elif fault_type == FaultType.LLM_CONNECTION_ERROR:
                    raise ConnectionError("Simulated LLM provider endpoint unreachable (503 Service Unavailable)")
                elif fault_type == FaultType.LLM_RATE_LIMIT:
                    raise RuntimeError("Simulated HTTP 429 Too Many Requests: Rate limit exceeded")
                elif fault_type == FaultType.LLM_MALFORMED_OUTPUT:
                    return "```json\n{ invalid_json: true, unterminated string"
                elif fault_type == FaultType.LLM_SCHEMA_INVALID:
                    return '{"invalid_key": 123, "rooms": "not_a_list"}'
                elif fault_type == FaultType.LLM_MISSING_CREDENTIALS:
                    raise PermissionError("Simulated HTTP 401 Unauthorized: Invalid API Key")
                elif fault_type == FaultType.LLM_REPEATED_INVALID:
                    return "Sorry, I cannot generate floor plans as an AI model."
            if original_generate:
                return original_generate(*args, **kwargs)
            return "{}"

        with patch.object(client, "generate", side_effect=faulty_generate):
            yield calls

    @staticmethod
    def create_exhausted_budget(max_steps: int = 1, max_tools: int = 1) -> Budget:
        """Create an immediately exhaustible budget for testing bounded execution limits."""
        return Budget(
            max_steps=max_steps,
            max_llm_calls=1,
            max_tool_calls=max_tools,
            max_wall_seconds=1.0,
            steps_used=max_steps,
            tool_calls_used=max_tools,
        )

    @staticmethod
    def simulate_stale_proposal(proposal: Any, delta_version: int = -1) -> Any:
        """Modify proposal's state_version to simulate concurrent stale proposals."""
        proposal.state_version = max(1, getattr(proposal, "state_version", 1) + delta_version)
        return proposal

    @staticmethod
    def create_degenerate_geometry(floor_number: int = 1) -> Geometry:
        """Create a mathematically degenerate Geometry (self-intersecting room polygon) for failure testing."""
        room = GeoRoom(
            id="georoom_degenerate_01",
            room_type="living",
            usable_polygon=[(0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)],  # Self-intersecting bowtie
            built_polygon=[(0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)],
            area_sqm=50.0,
            floor_number=floor_number,
        )
        return Geometry(
            id="geo_degenerate_01",
            floor_number=floor_number,
            rooms=[room],
            walls=[],
            doors=[],
            windows=[],
            plot_polygon=[(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)],
            buildable_polygon=[(2.0, 2.0), (18.0, 2.0), (18.0, 18.0), (2.0, 18.0)],
        )
