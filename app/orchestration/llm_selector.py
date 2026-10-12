"""LLM-backed action selector for PlanForge agentic orchestration.

Analyzes the current ProjectState, interprets intermediate tool outcomes and
validation findings, and uses the configured LLM to select the next action.
Includes schema validation, anti-oscillation checks, and deterministic fallback behavior.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agentic.budget import Budget
from app.agentic.events import InMemoryEventLog
from app.agentic.state import DecisionRecord, Finding, ProjectState, RunStatus
from app.agentic.tools import ToolRegistry, ToolSpec
from app.agentic.util import to_jsonable
from app.llm.client import HuggingFaceError, LLMClient, MockLLMClient
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.llm.response_parser import LLMResponseParser
from app.orchestration.routing import AgenticPolicy, NextAction

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Architectural Action Selector for PlanForge AI, an agentic system generating code-compliant, physically realizable residential floor plans.
Your role: Observe current project state, evaluate evidence from previous tool executions and validation reports, and decide the single most appropriate NEXT ACTION.

Available Actions:
- Registered Domain Tools:
  - "parse_requirements": Parse brief or validate requirements. Arguments: {"raw_brief": str, "project_name": str}
  - "check_feasibility": Check site boundary, setbacks, and room area budget. Arguments: {}
  - "plan_spatial_program": Formulate spatial program and zoning strategy. Arguments: {"strategy": "balanced" | "compact" | "circulation_prioritized"}
  - "allocate_spatial_regions": Run ASAA spatial allocation. Arguments: {"seed": int, "num_candidates": int}
  - "design_architecture": Generate architectural room designs, doors, and windows. Arguments: {"strategy": "standard" | "open_concept" | "private"}
  - "construct_geometry": Construct authoritative Shapely 2D geometry from layout proposals. Arguments: {}
  - "validate_design": Run authoritative FloorPlanValidator on constructed geometry. Arguments: {}
  - "refine_design": Perform targeted geometric refinement for detected issues. Arguments: {"action": "full_loop" | "fix_doors" | "fix_windows", "max_iterations": int}
  - "generate_alternatives": Generate diverse floor plan alternatives. Arguments: {"num_alternatives": int}
  - "export_bundle": Export DXF, images, and project documentation bundle. Arguments: {"output_dir": str}

- Workflow Control Actions:
  - "finish": Floor plan is completely valid (0 hard validation errors, geometry constructed, validated, and exported). Arguments: {}
  - "declare_infeasible": Physical requirements cannot be satisfied (e.g. total minimum room area exceeds buildable plot area). Arguments: {"reason": str}
  - "request_clarification": Essential requirements are missing or ambiguous. Arguments: {"questions": list[str]}
  - "halt": Execution must stop due to repeated stalls or unrecoverable error. Arguments: {"reason": str}

Behavioral Rules:
1. Strict Validator Authority: Never finish if there are uncorrected hard validation errors or if geometry is not yet validated.
2. Evidence-Based Action Selection:
   - If geometry validation shows overlap or boundary issues, select "refine_design".
   - If refinement has failed repeatedly, change planning strategy via "plan_spatial_program" with "compact" or "circulation_prioritized".
   - If required room area exceeds available buildable plot area by a deficit, select "declare_infeasible".
   - If validation is completely clean (0 hard errors), proceed to "export_bundle" then "finish".
3. Valid Schemas: Only supply arguments matching the action's schema.
4. Response Format: Output ONLY a single JSON object matching this schema:
{
  "action": "<action_name>",
  "arguments": { ... },
  "reason_code": "<concise_category_code>",
  "evidence": ["<state_facts_or_finding_codes>"],
  "expected_outcome": "<what_this_action_will_accomplish>",
  "completion_assessment": "in_progress" | "ready_to_finish" | "infeasible" | "needs_clarification",
  "requires_user_input": false
}
"""


@dataclass
class ActionDecision:
    """Structured decision output expected from the LLM."""

    action: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    reason_code: str = "general_progress"
    evidence: List[str] = field(default_factory=list)
    expected_outcome: str = ""
    completion_assessment: str = "in_progress"
    requires_user_input: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "arguments": self.arguments,
            "reason_code": self.reason_code,
            "evidence": self.evidence,
            "expected_outcome": self.expected_outcome,
            "completion_assessment": self.completion_assessment,
            "requires_user_input": self.requires_user_input,
        }


def build_decision_context(state: ProjectState, registry: ToolRegistry) -> Dict[str, Any]:
    """Assemble a rich, sanitized context dictionary for the LLM action selector.

    No internal secrets or raw credentials are ever included.
    """
    legal_specs = registry.legal(state)
    legal_names = [s.name for s in legal_specs]

    # Blocked tools with reasons
    blocked_tools: Dict[str, List[str]] = {}
    for name in registry.names():
        spec = registry.get(name)
        if spec:
            blockers = spec.missing_preconditions(state)
            if blockers:
                blocked_tools[name] = blockers

    # Format requirements if present
    req = state.get_artifact("requirements")
    req_summary: Dict[str, Any] = {}
    if req:
        floors_list: List[Dict[str, Any]] = []
        total_min_area = 0.0
        for f in getattr(req, "floors", []):
            floor_num = getattr(f, "floor_number", 1)
            target_area = getattr(f, "total_area_sqm", None)
            rooms_for_floor = getattr(f, "room_requirements", [])
            rooms_list: List[Dict[str, Any]] = []
            for r in rooms_for_floor:
                rm_name = getattr(r, "description", "") or getattr(r, "room_type", "room")
                rm_type = getattr(r, "room_type", "room")
                min_a = float(getattr(r, "min_area_sqm", 0.0) or 0.0)
                max_a = float(getattr(r, "max_area_sqm", 0.0) or 0.0)
                total_min_area += min_a
                rooms_list.append({
                    "name": rm_name,
                    "type": rm_type,
                    "min_area": min_a,
                    "max_area": max_a,
                })
            floors_list.append({
                "floor_number": floor_num,
                "target_area": target_area,
                "rooms": rooms_list,
            })

        req_summary = {
            "project_name": getattr(req, "project_name", state.goal),
            "plot_dimensions": getattr(req, "plot_dimensions", None),
            "plot_shape": getattr(req, "plot_shape", None),
            "total_floors": len(floors_list),
            "floors": floors_list,
            "total_min_area": round(total_min_area, 2),
        }

    # Format top findings
    findings_summary: List[Dict[str, Any]] = []
    for f in state.hard_findings()[:8]:
        findings_summary.append(
            {
                "code": f.code,
                "severity": f.severity,
                "message": f.message,
                "target": f.target,
                "floor": f.floor,
                "suggested_actions": f.suggested_actions,
            }
        )

    # Recent tool history
    recent_tools: List[Dict[str, Any]] = []
    for tc in state.tool_calls[-5:]:
        recent_tools.append(
            {
                "tool": tc.tool,
                "ok": tc.ok,
                "outcome": tc.outcome,
                "summary": tc.summary[:150],
                "error_type": tc.error_type,
            }
        )

    # Defect diagnosis
    primary_category = "none"
    hard_findings = state.hard_findings()
    if hard_findings:
        codes_str = " ".join(f.code.lower() for f in hard_findings)
        if any(term in codes_str for term in ("adjacency", "separation", "relationship", "access")):
            primary_category = "zoning_adjacency"
        elif any(term in codes_str for term in ("area", "budget", "deficit")):
            primary_category = "allocation"
        elif any(term in codes_str for term in ("stair", "floor_connectivity", "vertical")):
            primary_category = "multifloor"
        elif any(term in codes_str for term in ("overlap", "boundary", "door", "window", "dimension")):
            primary_category = "geometry"
        else:
            primary_category = "geometry"

    cand_summary = {
        "has_valid_candidate": False,
        "total_candidates": 0,
        "best_candidate_id": None,
        "best_candidate_score": None,
    }
    if hasattr(state, "candidate_manager") and state.candidate_manager is not None:
        cand_summary["has_valid_candidate"] = state.candidate_manager.has_valid_candidate()
        cand_summary["total_candidates"] = len(state.candidate_manager.candidates)
        if state.candidate_manager.best_record is not None:
            cand_summary["best_candidate_id"] = state.candidate_manager.best_record.candidate_id
            cand_summary["best_candidate_score"] = state.candidate_manager.best_record.evaluation.validation_score

    return {
        "project_id": state.project_id,
        "goal": state.goal,
        "step": state.step,
        "status": state.status.value,
        "planning_strategy": state.strategy.get("planning_strategy", "balanced"),
        "artifacts_present": sorted(list(state.artifacts.keys())),
        "requirements": req_summary,
        "num_alternatives": state.inputs.get("num_alternatives", 1),
        "facts": {
            "feasibility_checked": state.facts.get("feasibility_checked", False),
            "feasible": state.facts.get("feasible", None),
            "deficits": state.facts.get("deficits", []),
            "validation_score": state.facts.get("validation_score"),
            "export_bundle_path": bool(state.facts.get("export_bundle_path")),
        },
        "validation": {
            "is_current": state.validation_is_current(),
            "hard_errors_count": len(state.hard_findings()),
            "warnings_count": len(state.warning_findings()),
            "top_findings": findings_summary,
        },
        "defect_diagnosis": {
            "primary_category": primary_category,
            "hard_errors_count": len(hard_findings),
        },
        "candidate_summary": cand_summary,
        "recent_tool_calls": recent_tools,
        "blocked_actions": state.blocked_actions(),
        "open_questions": list(state.open_questions),
        "infeasibility_evidence": state.infeasibility_evidence,
        "legal_tools": legal_names,
        "blocked_tools": blocked_tools,
        "budget_remaining": state.budget.remaining(),
    }


def deterministic_mock_selector_generator(prompt: str, system_prompt: Optional[str] = None) -> str:
    """State-aware deterministic mock generator for test environments.

    Analyzes embedded context in prompt and produces accurate structured JSON decisions.
    """
    context: Dict[str, Any] = {}
    try:
        context = LLMResponseParser.parse_json(prompt)
    except Exception:
        pass

    # 1. Check for open questions or incomplete brief
    open_questions = context.get("open_questions", [])
    if open_questions:
        return json.dumps({
            "action": "request_clarification",
            "arguments": {"questions": list(open_questions)},
            "reason_code": "user_clarification_required",
            "evidence": ["open_questions_pending"],
            "expected_outcome": "Clarified architectural requirements",
            "completion_assessment": "needs_clarification",
            "requires_user_input": True,
        })

    facts = context.get("facts", {})
    artifacts = context.get("artifacts_present", [])

    # 2. Check for explicit area infeasibility / deficit
    if facts.get("feasible") is False:
        deficits = facts.get("deficits", [])
        return json.dumps({
            "action": "declare_infeasible",
            "arguments": {"reason": f"Required floor area exceeds available buildable site capacity: {deficits}"},
            "reason_code": "area_deficit_infeasible",
            "evidence": ["physical_site_deficit"],
            "expected_outcome": "Clean and honest infeasibility declaration",
            "completion_assessment": "infeasible",
            "requires_user_input": False,
        })

    # 3. Missing requirements
    if "requirements" not in artifacts:
        return json.dumps({
            "action": "parse_requirements",
            "arguments": {},
            "reason_code": "parse_brief",
            "evidence": ["raw_brief_provided"],
            "expected_outcome": "Normalized Requirements object",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 4. Feasibility not checked
    if not facts.get("feasibility_checked", False):
        return json.dumps({
            "action": "check_feasibility",
            "arguments": {},
            "reason_code": "site_capacity_check",
            "evidence": ["unverified_site_capacity"],
            "expected_outcome": "Verified site footprint and buildable boundaries",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 5. Planning spec missing
    if "planning_spec" not in artifacts:
        strat = context.get("planning_strategy", "balanced")
        return json.dumps({
            "action": "plan_spatial_program",
            "arguments": {"strategy": strat},
            "reason_code": "plan_spatial_program",
            "evidence": ["requirements_verified"],
            "expected_outcome": f"Formulated PlanningSpec spatial program using {strat} strategy",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 6. Allocation missing
    if "allocation_set" not in artifacts:
        alloc_count = sum(1 for tc in context.get("recent_tool_calls", []) if tc.get("tool") == "allocate_spatial_regions")
        seed = 42 + alloc_count
        return json.dumps({
            "action": "allocate_spatial_regions",
            "arguments": {"seed": seed, "num_candidates": 1},
            "reason_code": "asaa_spatial_allocation",
            "evidence": ["planning_spec_available"],
            "expected_outcome": "ASAA spatial regions allocated",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 7. Architectural design missing
    if "architectural_design_set" not in artifacts:
        return json.dumps({
            "action": "design_architecture",
            "arguments": {"strategy": "standard"},
            "reason_code": "architectural_room_design",
            "evidence": ["spatial_regions_allocated"],
            "expected_outcome": "Room designs with door and window placements",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 8. Geometry missing
    if "floor_plan_set" not in artifacts:
        return json.dumps({
            "action": "construct_geometry",
            "arguments": {},
            "reason_code": "construct_2d_geometry",
            "evidence": ["architectural_design_ready"],
            "expected_outcome": "Authoritative Shapely 2D floor plan geometry",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 9. Validation not current
    val_info = context.get("validation", {})
    if not val_info.get("is_current", False):
        return json.dumps({
            "action": "validate_design",
            "arguments": {},
            "reason_code": "independent_code_validation",
            "evidence": ["unvalidated_geometry"],
            "expected_outcome": "Deterministic FloorPlanValidator report",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 10. Hard validation errors
    if val_info.get("hard_errors_count", 0) > 0:
        defect_diag = context.get("defect_diagnosis", {})
        primary_cat = defect_diag.get("primary_category", "geometry")
        blocked_tools = context.get("blocked_tools", {})
        blocked_actions = [b.get("tool") for b in context.get("blocked_actions", [])]

        if primary_cat == "zoning_adjacency" and "plan_spatial_program" not in blocked_tools and "plan_spatial_program" not in blocked_actions:
            return json.dumps({
                "action": "plan_spatial_program",
                "arguments": {"strategy": "circulation_prioritized"},
                "reason_code": "strategic_replan_adjacency_defect",
                "evidence": ["adjacency_defect_detected"],
                "expected_outcome": "Reformulate spatial program with circulation priorities",
                "completion_assessment": "in_progress",
                "requires_user_input": False,
            })
        elif primary_cat == "allocation" and "allocate_spatial_regions" not in blocked_tools and "allocate_spatial_regions" not in blocked_actions:
            alloc_count = sum(1 for tc in context.get("recent_tool_calls", []) if tc.get("tool") == "allocate_spatial_regions")
            new_seed = 42 + (alloc_count + 1) * 7
            return json.dumps({
                "action": "allocate_spatial_regions",
                "arguments": {"seed": new_seed, "num_candidates": 2},
                "reason_code": "reallocation_for_area_defect",
                "evidence": ["area_allocation_defect_detected"],
                "expected_outcome": f"Reallocate spatial regions using variation seed {new_seed}",
                "completion_assessment": "in_progress",
                "requires_user_input": False,
            })
        else:
            if "refine_design" in blocked_tools or "refine_design" in blocked_actions:
                return json.dumps({
                    "action": "plan_spatial_program",
                    "arguments": {"strategy": "compact"},
                    "reason_code": "strategic_replan_after_refinement_stall",
                    "evidence": ["refinement_ineffective"],
                    "expected_outcome": "Compact spatial program to resolve persistent constraints",
                    "completion_assessment": "in_progress",
                    "requires_user_input": False,
                })
            return json.dumps({
                "action": "refine_design",
                "arguments": {"action": "full_loop", "max_iterations": 2},
                "reason_code": "targeted_geometric_refinement",
                "evidence": ["hard_validation_errors_present"],
                "expected_outcome": "Adjusted room geometries to eliminate errors",
                "completion_assessment": "in_progress",
                "requires_user_input": False,
            })

    # 11. Clean validation: check alternatives
    num_alts = context.get("num_alternatives", 1)
    if num_alts > 1 and "alternative_set" not in artifacts:
        return json.dumps({
            "action": "generate_alternatives",
            "arguments": {"num_alternatives": num_alts},
            "reason_code": "generate_design_variations",
            "evidence": ["base_plan_valid"],
            "expected_outcome": f"Generate {num_alts} diverse architectural design alternatives",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # Check exports
    if not facts.get("export_bundle_path"):
        return json.dumps({
            "action": "export_bundle",
            "arguments": {"output_dir": "outputs"},
            "reason_code": "cad_bundle_export",
            "evidence": ["geometry_validated_clean"],
            "expected_outcome": "DXF, SVG, and JSON bundles written",
            "completion_assessment": "in_progress",
            "requires_user_input": False,
        })

    # 12. Complete and verified!
    return json.dumps({
        "action": "finish",
        "arguments": {},
        "reason_code": "all_acceptance_criteria_satisfied",
        "evidence": ["zero_hard_errors", "exports_complete"],
        "expected_outcome": "Final verified floor plan design milestone accepted",
        "completion_assessment": "ready_to_finish",
        "requires_user_input": False,
    })


class LLMActionSelector:
    """Action selector that uses the configured LLM to choose the next workflow step.

    Applies schema validation, security bounds, anti-oscillation checks, and
    deterministic fallback behavior when the LLM is unavailable or produces invalid output.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        fallback_policy: Optional[AgenticPolicy] = None,
        llm_client: Optional[LLMClient] = None,
        config: Optional[LLMConfig] = None,
        event_log: Optional[InMemoryEventLog] = None,
    ) -> None:
        self.registry = registry
        self.fallback_policy = fallback_policy or AgenticPolicy()
        self.config = config or LLMConfig.from_env()
        self.event_log = event_log or InMemoryEventLog()

        if llm_client is not None:
            self.client = llm_client
        else:
            if self.config.provider == "mock":
                self.client = MockLLMClient(generator=deterministic_mock_selector_generator)
            else:
                try:
                    self.client = create_llm_client(self.config)
                except ValueError:
                    logger.warning(
                        "Unsupported provider '%s' passed to LLMActionSelector; falling back to deterministic mock selector",
                        self.config.provider,
                    )
                    self.client = MockLLMClient(generator=deterministic_mock_selector_generator)

    @property
    def provider_mode(self) -> str:
        """Observable provider execution mode ('mock' or 'live')."""
        return "mock" if isinstance(self.client, MockLLMClient) else "live"

    @property
    def model_name(self) -> str:
        """Sanitized model name."""
        return getattr(self.config, "model_name", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")

    def decide(self, state: ProjectState) -> NextAction:
        """Inspect state and consult LLM to determine next action with guaranteed fallback."""
        # 1. Budget checks
        budget_reason = state.budget.exhausted()
        if budget_reason:
            return NextAction(
                tool=None,
                args={},
                rationale=f"Budget exhausted: {budget_reason}",
                kind="halt",
                target_status=RunStatus.BUDGET_EXHAUSTED,
                source="rules",
            )

        if state.budget.llm_calls_used >= state.budget.max_llm_calls:
            fb_reason = f"LLM-call budget exhausted ({state.budget.llm_calls_used}/{state.budget.max_llm_calls})"
            self.event_log.emit(
                type="fallback_activated",
                agent="action_selector",
                summary="Activating deterministic fallback policy: LLM budget exhausted",
                data={"reason": "llm_budget_exhausted", "used": state.budget.llm_calls_used},
            )
            fb_action = self.fallback_policy.decide(state)
            fb_action.source = "fallback"
            fb_action.fallback_reason = fb_reason
            return fb_action

        # 2. Build sanitized context
        context = build_decision_context(state, self.registry)
        user_prompt = f"Current Project State:\n{json.dumps(context, indent=2)}\n\nSelect the next best action as JSON."

        self.event_log.emit(
            type="llm_decision_requested",
            agent="action_selector",
            summary=f"Requesting LLM action selection ({self.provider_mode} mode)",
            data={
                "provider": getattr(self.config, "provider", "mock"),
                "mode": self.provider_mode,
                "model": self.model_name,
                "step": state.step,
            },
        )

        state.budget.llm_calls_used += 1
        t_start = time.perf_counter()

        # 3. Call LLM
        try:
            response_text = self.client.generate(prompt=user_prompt, system_prompt=SYSTEM_PROMPT)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            self.event_log.emit(
                type="llm_response_received",
                agent="action_selector",
                summary="Received LLM decision response",
                data={"duration_ms": round(elapsed_ms, 2), "chars": len(response_text)},
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            err_type = type(e).__name__
            err_msg = str(e)
            logger.warning(f"LLM provider failed ({err_type}): {err_msg}")

            self.event_log.emit(
                type="llm_decision_failed",
                agent="action_selector",
                summary=f"LLM provider error: {err_type}",
                data={"error_type": "provider_error", "exception": err_type, "message": err_msg[:200]},
            )
            self.event_log.emit(
                type="fallback_activated",
                agent="action_selector",
                summary="Activating deterministic fallback policy due to provider error",
                data={"reason": f"provider_error_{err_type}"},
            )
            fb_action = self.fallback_policy.decide(state)
            fb_action.source = "fallback"
            fb_action.fallback_reason = f"Provider error: {err_type} - {err_msg[:100]}"
            return fb_action

        # 4. Parse JSON
        try:
            parsed = LLMResponseParser.parse_json(response_text)
        except Exception as e:
            logger.warning(f"Failed to parse LLM response JSON: {e}")
            self.event_log.emit(
                type="llm_decision_failed",
                agent="action_selector",
                summary="LLM response did not contain valid JSON",
                data={"error_type": "malformed_json", "error": str(e)},
            )
            self.event_log.emit(
                type="fallback_activated",
                agent="action_selector",
                summary="Activating deterministic fallback policy due to malformed response",
                data={"reason": "malformed_json"},
            )
            fb_action = self.fallback_policy.decide(state)
            fb_action.source = "fallback"
            fb_action.fallback_reason = f"Malformed JSON from LLM: {str(e)[:100]}"
            return fb_action

        # 5. Validate Decision
        return self._validate_and_build_action(parsed, state)

    def _validate_and_build_action(self, parsed: Dict[str, Any], state: ProjectState) -> NextAction:
        """Validate LLM action proposal against schema, permissions, and hard invariants."""
        action_name = str(parsed.get("action", "")).strip()
        args = dict(parsed.get("arguments", {}))
        reason_code = str(parsed.get("reason_code", "general_step"))
        evidence = [str(x) for x in parsed.get("evidence", [])]
        expected_outcome = str(parsed.get("expected_outcome", ""))
        completion_assessment = str(parsed.get("completion_assessment", "in_progress"))
        requires_user_input = bool(parsed.get("requires_user_input", False))

        # Handle special control actions
        if action_name == "declare_infeasible":
            reason = str(args.get("reason", expected_outcome or "Declared infeasible by LLM reasoning."))
            self.event_log.emit(
                type="decision_validated",
                agent="action_selector",
                summary=f"Validated LLM decision: Infeasible ({reason_code})",
                data={"action": action_name, "reason_code": reason_code},
            )
            return NextAction(
                tool=None,
                args=args,
                rationale=reason,
                kind="finish",
                target_status=RunStatus.INFEASIBLE,
                source="llm",
                reason_code=reason_code,
                evidence=evidence,
                expected_outcome=expected_outcome,
            )

        if action_name == "request_clarification":
            questions = list(args.get("questions", ["User clarification required."]))
            self.event_log.emit(
                type="decision_validated",
                agent="action_selector",
                summary=f"Validated LLM decision: Request clarification ({reason_code})",
                data={"action": action_name, "questions": questions},
            )
            return NextAction(
                tool=None,
                args=args,
                rationale="; ".join(questions),
                kind="halt",
                target_status=RunStatus.NEEDS_CLARIFICATION,
                source="llm",
                reason_code=reason_code,
                evidence=evidence,
                expected_outcome=expected_outcome,
                requires_user_input=True,
            )

        if action_name == "halt":
            reason = str(args.get("reason", expected_outcome or "Halted by LLM."))
            self.event_log.emit(
                type="decision_validated",
                agent="action_selector",
                summary=f"Validated LLM decision: Halt ({reason_code})",
                data={"action": action_name, "reason": reason},
            )
            return NextAction(
                tool=None,
                args=args,
                rationale=reason,
                kind="halt",
                target_status=RunStatus.STALLED,
                source="llm",
                reason_code=reason_code,
                evidence=evidence,
                expected_outcome=expected_outcome,
            )

        if action_name == "finish":
            # HARD INVARIANT: Cannot finish if hard validation errors remain!
            hard_errors = state.hard_findings()
            if hard_errors:
                self.event_log.emit(
                    type="decision_rejected",
                    agent="action_selector",
                    summary="LLM attempted to finish while hard validation errors remain",
                    data={"hard_errors": len(hard_errors), "reason": "unresolved_hard_errors"},
                )
                self.event_log.emit(
                    type="fallback_activated",
                    agent="action_selector",
                    summary="Activating deterministic fallback to resolve remaining hard errors",
                    data={"reason": "invalid_finish_with_hard_errors"},
                )
                fb_action = self.fallback_policy.decide(state)
                fb_action.source = "fallback"
                fb_action.fallback_reason = "Rejected finish: Hard validation errors still active"
                return fb_action

            if not state.has_artifact("floor_plan_set"):
                self.event_log.emit(
                    type="decision_rejected",
                    agent="action_selector",
                    summary="LLM attempted to finish before floor plan geometry was constructed",
                    data={"reason": "missing_geometry"},
                )
                fb_action = self.fallback_policy.decide(state)
                fb_action.source = "fallback"
                fb_action.fallback_reason = "Rejected finish: Geometry not yet constructed"
                return fb_action

            # Clean finish accepted
            score = state.facts.get("validation_score", 100.0)
            self.event_log.emit(
                type="decision_validated",
                agent="action_selector",
                summary="Validated LLM decision: Final acceptance",
                data={"action": "finish", "score": score},
            )
            return NextAction(
                tool=None,
                args={},
                rationale=expected_outcome or f"Floor plan validated with 0 hard errors (score {score:.1f}/100).",
                kind="finish",
                target_status=RunStatus.ACCEPTED,
                source="llm",
                reason_code=reason_code,
                evidence=evidence,
                expected_outcome=expected_outcome,
                completion_assessment="ready_to_finish",
            )

        # Check registered tool
        spec = self.registry.get(action_name)
        if spec is None:
            self.event_log.emit(
                type="decision_rejected",
                agent="action_selector",
                summary=f"LLM proposed unknown tool '{action_name}'",
                data={"unknown_tool": action_name},
            )
            self.event_log.emit(
                type="fallback_activated",
                agent="action_selector",
                summary="Activating fallback policy due to unknown tool",
                data={"reason": f"unknown_tool_{action_name}"},
            )
            fb_action = self.fallback_policy.decide(state)
            fb_action.source = "fallback"
            fb_action.fallback_reason = f"Unknown tool '{action_name}' proposed by LLM"
            return fb_action

        # Check preconditions and argument schema
        call_error = self.registry.check_call(state, action_name, args)
        if call_error is not None:
            self.event_log.emit(
                type="decision_rejected",
                agent="action_selector",
                summary=f"LLM proposed illegal call for '{action_name}': {call_error}",
                data={"tool": action_name, "error": call_error},
            )
            self.event_log.emit(
                type="fallback_activated",
                agent="action_selector",
                summary=f"Activating fallback policy due to illegal call on '{action_name}'",
                data={"reason": call_error},
            )
            fb_action = self.fallback_policy.decide(state)
            fb_action.source = "fallback"
            fb_action.fallback_reason = f"Illegal call for '{action_name}': {call_error}"
            return fb_action

        # Check anti-oscillation blocking
        action_key = f"{action_name}:{sorted(args.items())}"
        if action_key in state.blocked_keys():
            self.event_log.emit(
                type="decision_rejected",
                agent="action_selector",
                summary=f"Action '{action_name}' is blocked to prevent infinite cycle",
                data={"action_key": action_key},
            )
            self.event_log.emit(
                type="fallback_activated",
                agent="action_selector",
                summary="Activating fallback policy to break oscillation",
                data={"reason": "anti_oscillation_block"},
            )
            fb_action = self.fallback_policy.decide(state)
            fb_action.source = "fallback"
            fb_action.fallback_reason = f"Action '{action_name}' blocked by anti-oscillation safeguards"
            return fb_action

        # Valid action selected by LLM!
        self.event_log.emit(
            type="decision_validated",
            agent="action_selector",
            summary=f"Validated LLM action '{action_name}' ({reason_code})",
            data={
                "tool": action_name,
                "reason_code": reason_code,
                "evidence": evidence,
                "args": args,
            },
        )
        return NextAction(
            tool=action_name,
            args=args,
            rationale=expected_outcome or f"LLM selected '{action_name}' ({reason_code})",
            kind="tool_call",
            source="llm",
            reason_code=reason_code,
            evidence=evidence,
            expected_outcome=expected_outcome,
            completion_assessment=completion_assessment,
            requires_user_input=requires_user_input,
        )
