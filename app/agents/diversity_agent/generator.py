"""Multi-Design Generator coordinating architectural diversity exploration.

Generates multiple valid, structurally diverse residential floor plan alternatives
using different architectural strategies, full geometry construction, independent
validation, iterative refinement, and deterministic duplicate filtering.
"""

from __future__ import annotations
from typing import List, Optional, Tuple
from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.diversity_agent.metrics import (
    calculate_diversity_distance,
    is_duplicate,
    is_near_duplicate,
)
from app.agents.diversity_agent.signature import DesignSignatureBuilder
from app.agents.refinement_agent.loop import RefinementLoop
from app.geometry.engine import GeometryEngine
from app.models.allocation import AllocationSet
from app.models.alternatives import (
    AlternativeStatus,
    DesignAlternative,
    DesignAlternativeSet,
    DesignStrategy,
    RejectionReason,
)
from app.models.planning import PlanningSpec
from app.models.refinement import RefinementStatus
from app.models.requirements import Requirements
from app.utils.ids import generate_id
from app.validation.validator import FloorPlanValidator

Point2D = Tuple[float, float]

DEFAULT_STRATEGIES = [
    DesignStrategy.SOCIAL_CENTRIC.value,
    DesignStrategy.CORRIDOR_CENTRIC.value,
    DesignStrategy.COMPACT_CIRCULATION.value,
    DesignStrategy.PRIVACY_CENTRIC.value,
    DesignStrategy.OPEN_SOCIAL.value,
    DesignStrategy.SERVICE_CLUSTERED.value,
]


class MultiDesignGenerator:
    """Orchestrator for generating multiple diverse, validated residential floor plan alternatives."""

    def __init__(
        self,
        architectural_agent: Optional[ArchitecturalAgent] = None,
        refinement_loop: Optional[RefinementLoop] = None,
        geometry_engine: Optional[GeometryEngine] = None,
        validator: Optional[FloorPlanValidator] = None,
    ):
        """Initialize MultiDesignGenerator with modular pipeline components.

        Args:
            architectural_agent: Optional ArchitecturalAgent. Defaults to standard agent with mock.
            refinement_loop: Optional RefinementLoop. Defaults to standard loop.
            geometry_engine: Optional GeometryEngine.
            validator: Optional FloorPlanValidator.
        """
        self.architectural_agent = architectural_agent or ArchitecturalAgent()
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.validator = validator or FloorPlanValidator()
        self.refinement_loop = refinement_loop or RefinementLoop(
            geometry_engine=self.geometry_engine,
            validator=self.validator,
        )

    def generate(
        self,
        planning_spec: PlanningSpec,
        allocation_set: AllocationSet,
        requirements: Optional[Requirements] = None,
        num_alternatives: int = 3,
        candidate_budget: int = 6,
        minimum_diversity_distance: float = 0.25,
        strategies: Optional[List[str]] = None,
        max_refinement_iterations: int = 3,
        project_name: str = "",
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
    ) -> DesignAlternativeSet:
        """Generate multiple validated, structurally diverse residential alternatives.

        Args:
            planning_spec: Strategic PlanningSpec from Planning Agent.
            allocation_set: Authoritative AllocationSet from ASAA.
            requirements: Upstream Requirements.
            num_alternatives: Target number of distinct valid alternatives (default: 3).
            candidate_budget: Maximum candidate designs to evaluate (default: 6).
            minimum_diversity_distance: Minimum structural distance required between accepted designs (default: 0.25).
            strategies: Optional custom list of strategies.
            max_refinement_iterations: Max refinement cycles per candidate (default: 3).
            project_name: Project name for reporting.
            plot_boundary: Optional plot boundary polygon.
            buildable_boundary: Optional setback buildable envelope.

        Returns:
            DesignAlternativeSet containing accepted alternatives and research audit logs.
        """
        strategy_pool = list(strategies) if strategies else list(DEFAULT_STRATEGIES)
        accepted: List[DesignAlternative] = []
        rejected: List[DesignAlternative] = []
        strategies_attempted: List[str] = []

        total_candidates = min(candidate_budget, max(len(strategy_pool), candidate_budget))

        for idx in range(total_candidates):
            strat = strategy_pool[idx % len(strategy_pool)]
            strategies_attempted.append(strat)
            alt_id = generate_id("alt")

            # 1. Architectural Intent Proposal
            try:
                raw_design_set = self.architectural_agent.design(
                    planning_spec=planning_spec,
                    allocation_set=allocation_set,
                    requirements=requirements,
                    strategy=strat,
                    alternative_index=idx,
                )
            except Exception as e:
                candidate = DesignAlternative(
                    alternative_id=alt_id,
                    index=idx + 1,
                    strategy=strat,
                    architectural_design=None,  # type: ignore
                    status=AlternativeStatus.REJECTED,
                    rejection_reason=RejectionReason.SCHEMA_FAILURE.value,
                    design_rationale=f"Failed to generate valid architectural design: {e}",
                )
                rejected.append(candidate)
                continue

            # 2. Invariant Verification: Allocation and Room Preservation
            invariant_violated = False
            invariant_reason = ""
            for floor_d in raw_design_set.designs:
                alloc = allocation_set.get_allocation(floor_d.floor_number)
                if not alloc:
                    invariant_violated = True
                    invariant_reason = f"Floor {floor_d.floor_number} missing in ASAA AllocationSet"
                    break
                alloc_reg_ids = {r.id for r in alloc.allocated_regions}
                for room in floor_d.rooms:
                    if room.allocated_region_id not in alloc_reg_ids:
                        invariant_violated = True
                        invariant_reason = f"Room {room.id} assigned to unknown allocation region {room.allocated_region_id}"
                        break
                if invariant_violated:
                    break

            if invariant_violated:
                candidate = DesignAlternative(
                    alternative_id=alt_id,
                    index=idx + 1,
                    strategy=strat,
                    architectural_design=raw_design_set,
                    status=AlternativeStatus.REJECTED,
                    rejection_reason=RejectionReason.INVARIANT_VIOLATION.value,
                    design_rationale=invariant_reason,
                )
                rejected.append(candidate)
                continue

            # 3. Geometry Construction, Validation, and Refinement Loop
            try:
                refinement_result = self.refinement_loop.run(
                    initial_design=raw_design_set,
                    allocation_set=allocation_set,
                    requirements=requirements,
                    planning_spec=planning_spec,
                    project_name=project_name,
                    plot_boundary=plot_boundary,
                    buildable_boundary=buildable_boundary,
                    target_strategy=strat,
                )
            except Exception as e:
                candidate = DesignAlternative(
                    alternative_id=alt_id,
                    index=idx + 1,
                    strategy=strat,
                    architectural_design=raw_design_set,
                    status=AlternativeStatus.REJECTED,
                    rejection_reason=RejectionReason.GEOMETRY_FAILURE.value,
                    design_rationale=f"Geometry construction failed: {e}",
                )
                rejected.append(candidate)
                continue

            final_design = refinement_result.final_design
            final_report = refinement_result.final_report
            final_floor_plans = refinement_result.final_floor_plan_set

            # 4. Validity Filtering
            if not refinement_result.is_valid:
                candidate = DesignAlternative(
                    alternative_id=alt_id,
                    index=idx + 1,
                    strategy=strat,
                    architectural_design=final_design,
                    floor_plan_set=final_floor_plans,
                    validation_report=final_report,
                    refinement_result=refinement_result,
                    status=AlternativeStatus.REJECTED,
                    rejection_reason=RejectionReason.VALIDATION_FAILURE.value,
                    design_rationale=f"Design failed validation: {refinement_result.termination_reason}",
                )
                rejected.append(candidate)
                continue

            # 5. Extract Structural DesignSignature
            sig = DesignSignatureBuilder.build(final_design)

            # 6. Duplicate & Near-Duplicate Filtering
            is_dup = False
            dup_reason = ""
            diversity_distances: dict[str, float] = {}

            for prev_alt in accepted:
                if not prev_alt.design_signature:
                    continue
                dist = calculate_diversity_distance(sig, prev_alt.design_signature)
                diversity_distances[prev_alt.alternative_id] = dist

                if dist == 0.0:
                    is_dup = True
                    dup_reason = RejectionReason.DUPLICATE.value
                    break
                elif dist < minimum_diversity_distance:
                    is_dup = True
                    dup_reason = RejectionReason.INSUFFICIENT_DIVERSITY.value
                    break

            if is_dup:
                candidate = DesignAlternative(
                    alternative_id=alt_id,
                    index=idx + 1,
                    strategy=strat,
                    architectural_design=final_design,
                    floor_plan_set=final_floor_plans,
                    validation_report=final_report,
                    refinement_result=refinement_result,
                    design_signature=sig,
                    diversity_scores=diversity_distances,
                    status=AlternativeStatus.DUPLICATE if dup_reason == RejectionReason.DUPLICATE.value else AlternativeStatus.INSUFFICIENT_DIVERSITY,
                    rejection_reason=dup_reason,
                    design_rationale=f"Candidate rejected: {dup_reason} (closest distance={min(diversity_distances.values(), default=0.0)})",
                )
                rejected.append(candidate)
                continue

            # 7. Qualified Distinct Alternative Accepted
            characteristics = self._derive_characteristics(strat, sig)
            final_status = AlternativeStatus.REFINED_AND_VALID if len(refinement_result.iterations) > 1 else AlternativeStatus.VALIDATED

            candidate = DesignAlternative(
                alternative_id=alt_id,
                index=len(accepted) + 1,
                strategy=strat,
                architectural_design=final_design,
                floor_plan_set=final_floor_plans,
                validation_report=final_report,
                refinement_result=refinement_result,
                design_signature=sig,
                diversity_scores=diversity_distances,
                status=final_status,
                rejection_reason=None,
                design_rationale=f"Successfully generated and validated alternative adhering to '{strat}' strategy",
                characteristics=characteristics,
            )
            accepted.append(candidate)

            # Check if requested target count has been satisfied
            if len(accepted) >= num_alternatives:
                break

        # Overall set status
        if len(accepted) >= num_alternatives:
            set_status = "COMPLETE"
        elif accepted:
            set_status = "INSUFFICIENT_DIVERSITY"
        else:
            set_status = "FAILED"

        summary = (
            f"Generated {len(accepted) + len(rejected)} candidates across {len(strategies_attempted)} strategy attempts. "
            f"Accepted {len(accepted)} distinct valid alternatives (requested: {num_alternatives}). "
            f"Rejected {len(rejected)} candidates."
        )

        return DesignAlternativeSet(
            id=generate_id("alt_set"),
            project_name=project_name,
            requested_count=num_alternatives,
            candidates_generated=len(accepted) + len(rejected),
            alternatives=accepted,
            rejected_candidates=rejected,
            strategies_attempted=strategies_attempted,
            status=set_status,
            generation_summary=summary,
        )

    @staticmethod
    def _derive_characteristics(strategy: str, signature: DesignSignature) -> List[str]:
        """Derive concise structured architectural characteristics for an alternative."""
        chars: List[str] = []
        chars.append(f"Strategy: {strategy.replace('_', ' ').title()}")
        chars.append(f"Circulation: {signature.circulation_type.replace('_', ' ').title()}")
        chars.append(f"Primary Entrance: {signature.entrance_room_type.title()}")
        if signature.social_sequence:
            chars.append(f"Social Sequence: {' → '.join(s.title() for s in signature.social_sequence)}")
        chars.append(f"Zoning: {signature.private_clustering.title()} private wing")
        return chars
