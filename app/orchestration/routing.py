"""Context-aware routing and decision policy for the agentic workflow.

Decides the next useful tool call or state transition based on current project observations:
- Detects missing requirements and questions.
- Checks physical area feasibility before expensive allocation.
- Routes to appropriate agents (planning, ASAA, architectural design, geometry, validation).
- Prescribes corrective action when validation detects hard errors.
- Detects stalls and triggers strategic replanning.
- Replaces rigid 10-stage execution with dynamic, context-driven control flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.agentic.state import DecisionRecord, ProjectState, RunStatus

logger = logging.getLogger(__name__)


@dataclass
class NextAction:
    """Action selected by the policy or LLM action selector."""

    tool: Optional[str]
    args: Dict[str, Any]
    rationale: str
    kind: str = "tool_call"  # "tool_call" | "finish" | "halt"
    target_status: Optional[RunStatus] = None
    source: str = "agentic_policy"
    reason_code: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    expected_outcome: Optional[str] = None
    completion_assessment: Optional[str] = None
    requires_user_input: bool = False
    fallback_reason: Optional[str] = None


class AgenticPolicy:
    """Context-aware decision engine for PlanForge AI."""

    def __init__(self, enable_refinement: bool = True, num_alternatives: int = 1, enable_exports: bool = True) -> None:
        self.enable_refinement = enable_refinement
        self.num_alternatives = num_alternatives
        self.enable_exports = enable_exports

    def decide(self, state: ProjectState) -> NextAction:
        """Examine current state and decide the next best action."""
        # 1. Terminal / Budget checks
        budget_reason = state.budget.exhausted()
        if budget_reason:
            return NextAction(
                tool=None,
                args={},
                rationale=f"Budget exhausted: {budget_reason}",
                kind="halt",
                target_status=RunStatus.BUDGET_EXHAUSTED,
            )

        # 2. Check if requirements are present
        if not state.has_artifact("requirements"):
            return NextAction(
                tool="parse_requirements",
                args={
                    "raw_brief": state.inputs.get("raw_brief", state.goal),
                    "project_name": state.inputs.get("project_name", "PlanForge Project"),
                },
                rationale="No structured requirements found; parsing natural language architectural brief.",
            )

        # 3. Check for open questions or incomplete requirements
        if state.open_questions:
            return NextAction(
                tool=None,
                args={},
                rationale=f"Clarification required from user: {'; '.join(state.open_questions)}",
                kind="halt",
                target_status=RunStatus.NEEDS_CLARIFICATION,
            )

        # 4. Check feasibility before spatial planning
        if not state.facts.get("feasibility_checked", False):
            state.facts["feasibility_checked"] = True
            return NextAction(
                tool="check_feasibility",
                args={},
                rationale="Checking plot area capacity and room area budget before spatial allocation.",
            )

        # If feasibility was checked and failed:
        if state.facts.get("feasible") is False:
            deficits = state.facts.get("deficits", [])
            return NextAction(
                tool=None,
                args={},
                rationale=f"Spatial requirements physically infeasible under plot constraints: {deficits}",
                kind="finish",
                target_status=RunStatus.INFEASIBLE,
            )

        # 5. Check if planning specification is present
        if not state.has_artifact("planning_spec"):
            strat = state.strategy.get("planning_strategy", "balanced")
            return NextAction(
                tool="plan_spatial_program",
                args={"strategy": strat},
                rationale=f"Synthesizing requirements into strategic planning spec using {strat} strategy.",
            )

        # 6. Check if ASAA spatial allocation is present
        if not state.has_artifact("allocation_set"):
            alloc_attempts = state.tool_call_count("allocate_spatial_regions")
            seed = 42 + alloc_attempts
            return NextAction(
                tool="allocate_spatial_regions",
                args={"seed": seed, "num_candidates": 1},
                rationale=f"Running ASAA spatial allocation (attempt {alloc_attempts + 1}, seed {seed}).",
            )

        # 7. Check if architectural design intent is present
        if not state.has_artifact("architectural_design_set"):
            arch_strat = state.strategy.get("architectural_strategy", "standard")
            return NextAction(
                tool="design_architecture",
                args={"strategy": arch_strat},
                rationale=f"Generating architectural room designs, doors, and windows using {arch_strat} strategy.",
            )

        # 8. Check if physical geometry is constructed
        if not state.has_artifact("floor_plan_set"):
            return NextAction(
                tool="construct_geometry",
                args={},
                rationale="Constructing authoritative Shapely 2D geometry from architectural proposals.",
            )

        # 9. Check if validation is current
        if not state.validation_is_current():
            return NextAction(
                tool="validate_design",
                args={},
                rationale="Executing independent deterministic verification on constructed geometry.",
            )

        # 10. Analyze validation findings
        hard_errors = state.hard_findings()
        if hard_errors:
            # We have hard errors that prevent acceptance
            refine_count = state.tool_call_count("refine_design")
            primary_codes = {f.code.lower() for f in hard_errors}

            # Category C: Adjacency and zoning defects -> trigger revised planning strategy
            if any("adjacency" in c or "relationship" in c or "separation" in c for c in primary_codes):
                replan_count = state.strategy.get("replan_count", 0)
                if replan_count < 2:
                    state.strategy["replan_count"] = replan_count + 1
                    new_strat = "circulation_prioritized"
                    state.strategy["planning_strategy"] = new_strat
                    state.artifacts.pop("planning_spec", None)
                    state.artifacts.pop("allocation_set", None)
                    state.artifacts.pop("architectural_design_set", None)
                    state.artifacts.pop("floor_plan_set", None)
                    state.has_findings = False
                    return NextAction(
                        tool="plan_spatial_program",
                        args={"strategy": new_strat},
                        rationale=f"Adjacency/zoning defect detected ({', '.join(primary_codes)}); replanning spatial program with '{new_strat}' strategy.",
                        reason_code="replan_zoning_adjacency",
                        evidence=list(primary_codes),
                    )

            # Category B: Area and allocation defects -> trigger ASAA reallocation
            if any("area" in c or "budget" in c for c in primary_codes):
                alloc_attempts = state.tool_call_count("allocate_spatial_regions")
                if alloc_attempts < 3:
                    seed = 42 + alloc_attempts * 7
                    state.artifacts.pop("allocation_set", None)
                    state.artifacts.pop("architectural_design_set", None)
                    state.artifacts.pop("floor_plan_set", None)
                    state.has_findings = False
                    return NextAction(
                        tool="allocate_spatial_regions",
                        args={"seed": seed, "num_candidates": 2},
                        rationale=f"Room area/allocation defect detected ({', '.join(primary_codes)}); reallocating spatial regions with alternative seed {seed}.",
                        reason_code="reallocate_asaa_area_fit",
                        evidence=list(primary_codes),
                    )

            # Category A: Geometry, door, window, or overlap issues -> targeted refinement
            if self.enable_refinement and refine_count < 3 and not state.stalled:
                return NextAction(
                    tool="refine_design",
                    args={"action": "full_loop", "max_iterations": 2},
                    rationale=f"Attempting refinement to correct {len(hard_errors)} hard issue(s) ({', '.join(primary_codes)}).",
                    reason_code="targeted_geometry_refinement",
                    evidence=list(primary_codes),
                )

            # If refinement has already been tried and stalled, or boundary/dimension issues persist:
            replan_count = state.strategy.get("replan_count", 0)
            if replan_count < 2:
                # Trigger strategic replanning!
                state.strategy["replan_count"] = replan_count + 1
                new_strat = "compact" if replan_count == 0 else "circulation_prioritized"
                state.strategy["planning_strategy"] = new_strat

                # Invalidate downstream artifacts so the pipeline regenerates cleanly
                state.artifacts.pop("planning_spec", None)
                state.artifacts.pop("allocation_set", None)
                state.artifacts.pop("architectural_design_set", None)
                state.artifacts.pop("floor_plan_set", None)
                state.has_findings = False

                return NextAction(
                    tool="plan_spatial_program",
                    args={"strategy": new_strat},
                    rationale=f"Refinement did not resolve issues; replanning spatial program with '{new_strat}' strategy (replan {replan_count + 1}).",
                    reason_code="strategic_replan_fallback",
                    evidence=list(primary_codes),
                )

            # If all replanning and refinement attempts are exhausted:
            # Report infeasibility honestly! Never pretend invalid designs are valid.
            err_msgs = [f.message for f in hard_errors[:3]]
            return NextAction(
                tool=None,
                args={},
                rationale=f"Cannot satisfy hard constraints after refinement and replanning attempts: {'; '.join(err_msgs)}",
                kind="finish",
                target_status=RunStatus.INFEASIBLE,
            )

        # 11. Validation is clean (0 hard errors)! Check optional stages
        if self.num_alternatives > 1 and not state.has_artifact("alternative_set"):
            return NextAction(
                tool="generate_alternatives",
                args={"num_alternatives": self.num_alternatives},
                rationale=f"Valid base floor plan established; generating {self.num_alternatives} diverse design alternatives.",
            )

        if self.enable_exports and not state.facts.get("export_bundle_path"):
            return NextAction(
                tool="export_bundle",
                args={"output_dir": state.inputs.get("output_dir", "outputs")},
                rationale="Exporting authoritative project CAD DXF, images, and report bundle.",
            )

        # 12. Final Acceptance!
        score = state.facts.get("validation_score", 100.0)
        return NextAction(
            tool=None,
            args={},
            rationale=f"Floor plan successfully validated with 0 hard errors and quality score {score:.1f}/100.",
            kind="finish",
            target_status=RunStatus.ACCEPTED,
        )
