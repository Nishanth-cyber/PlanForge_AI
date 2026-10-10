
"""Central PlanForge pipeline orchestrator coordinating all 10 generation stages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type

from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.diversity_agent import MultiDesignGenerator
from app.agents.planning_agent import PlanningAgent
from app.agents.refinement_agent import RefinementLoop, RefinementStatus
from app.agents.requirement_agent import RequirementAgent
from app.agents.requirement_agent.completeness_gate import CompletenessGate
from app.asaa.allocator import ASAAAllocator
from app.explainability.builder import DecisionTraceBuilder
from app.export.bundle_exporter import BundleExporter, export_project_bundle
from app.export.integrity import verify_export_integrity
from app.geometry.engine import GeometryEngine
from app.models.alternatives import (
    AlternativeStatus,
    DesignAlternative,
    DesignAlternativeSet,
)
from app.models.requirements import Requirements
from app.orchestration.config import OrchestrationConfig
from app.orchestration.errors import (
    IncompleteRequirementsError,
    OrchestrationError,
    StageExecutionError,
)
from app.orchestration.pipeline import PipelineResult
from app.orchestration.state import PipelineState, StageName, StageStatus
from app.utils.ids import generate_id
from app.validation.validator import FloorPlanValidator

logger = logging.getLogger(__name__)


class PlanForgeOrchestrator:
    """Coordinates end-to-end execution of the 10-stage PlanForge architecture.

    Strict Architectural Invariants:
    1. Orchestration coordinates but does not implement domain logic.
    2. All algorithmic components (ASAA, Geometry, Validation, Refinement, Diversity,
       Trace, Export) are delegated to their authoritative sub-systems.
    3. Full dependency injection: every component can be provided at initialization
       or defaults to standard offline implementations.
    4. Completeness Gate is authoritative: incomplete requirements stop generation immediately.
    5. Zero fabrication: No rooms, dimensions, floors, or winners are synthesized.
    6. Unrecoverable stage failures cleanly skip subsequent dependent stages.
    """

    def __init__(
        self,
        requirement_agent: Optional[RequirementAgent] = None,
        planning_agent: Optional[PlanningAgent] = None,
        asaa_allocator: Optional[ASAAAllocator] = None,
        architectural_agent: Optional[ArchitecturalAgent] = None,
        geometry_engine: Optional[GeometryEngine] = None,
        validator: Optional[FloorPlanValidator] = None,
        refinement_loop: Optional[RefinementLoop] = None,
        diversity_generator: Optional[MultiDesignGenerator] = None,
        trace_builder: Optional[Type[DecisionTraceBuilder]] = None,
        exporter: Optional[BundleExporter] = None,
    ) -> None:
        self.requirement_agent = requirement_agent or RequirementAgent()
        self.planning_agent = planning_agent or PlanningAgent()
        self.asaa_allocator = asaa_allocator or ASAAAllocator(seed=42)
        self.architectural_agent = architectural_agent or ArchitecturalAgent()
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.validator = validator or FloorPlanValidator()
        self.refinement_loop = refinement_loop or RefinementLoop(
            geometry_engine=self.geometry_engine,
            validator=self.validator,
        )
        self.diversity_generator = diversity_generator or MultiDesignGenerator(
            architectural_agent=self.architectural_agent,
            refinement_loop=self.refinement_loop,
            geometry_engine=self.geometry_engine,
            validator=self.validator,
        )
        self.trace_builder = trace_builder or DecisionTraceBuilder
        self.exporter = exporter or BundleExporter()

    def generate(
        self,
        raw_brief: Optional[str] = None,
        requirements: Optional[Requirements] = None,
        project_name: str = "",
        project_id: Optional[str] = None,
        config: Optional[OrchestrationConfig] = None,
    ) -> PipelineResult:
        """Execute the complete generation pipeline according to configuration.

        Args:
            raw_brief: Freeform architectural prompt from user.
            requirements: Pre-parsed Requirements object (optional override).
            project_name: Project title.
            project_id: Optional existing ID. If None, generated automatically.
            config: Execution configuration. Defaults to standard OrchestrationConfig.

        Returns:
            PipelineResult containing all generated models, status, and diagnostics.
        """
        cfg = config or OrchestrationConfig()
        pid = project_id or generate_id("proj")
        pname = project_name or (requirements.project_name if requirements else "PlanForge Project")

        state = PipelineState(project_id=pid, project_name=pname, raw_brief=raw_brief)

        # ------------------------------------------------------------------
        # Stage 1: REQUIREMENT
        # ------------------------------------------------------------------
        state.start_stage(StageName.REQUIREMENT)
        try:
            if requirements is not None:
                state.requirements = requirements
                gate = CompletenessGate()
                state.completeness_result = gate.check(requirements)
            elif raw_brief:
                pipe_res = self.requirement_agent.process(raw_brief, project_name=pname)
                state.requirements = pipe_res.requirements
                state.completeness_result = pipe_res.completeness
            else:
                state.fail_stage(StageName.REQUIREMENT, "Neither raw_brief nor requirements provided.")
                state.skip_downstream_stages(StageName.REQUIREMENT)
                return self._create_result(state, status="failed", error="No requirements provided.")

            # Enforce Completeness Gate
            if state.completeness_result and not state.completeness_result.can_proceed:
                c = state.completeness_result
                msg = f"Requirements incomplete: {', '.join(c.missing_fields)}"
                if c.missing_floors:
                    msg += f"; missing rooms for floor(s): {c.missing_floors}"
                state.fail_stage(StageName.REQUIREMENT, msg)
                state.skip_downstream_stages(StageName.REQUIREMENT, reason="Requirements incomplete")
                return self._create_result(
                    state,
                    status="incomplete_requirements",
                    error=msg,
                    missing_fields=c.missing_fields,
                    missing_floors=c.missing_floors,
                    clarification_questions=c.clarification_questions,
                )

            state.complete_stage(
                StageName.REQUIREMENT,
                metadata={
                    "floors_count": len(state.requirements.floors) if state.requirements.floors else 1,
                    "total_rooms": state.requirements.total_rooms() if state.requirements else 0,
                },
            )
        except Exception as e:
            logger.exception("Error in REQUIREMENT stage")
            state.fail_stage(StageName.REQUIREMENT, str(e))
            state.skip_downstream_stages(StageName.REQUIREMENT)
            return self._create_result(state, status="failed", error=str(e))

        # ------------------------------------------------------------------
        # Stage 2: PLANNING
        # ------------------------------------------------------------------
        state.start_stage(StageName.PLANNING)
        try:
            state.planning_spec = self.planning_agent.plan(state.requirements)
            state.complete_stage(
                StageName.PLANNING,
                metadata={"programmed_floors": len(state.planning_spec.floors)},
            )
        except Exception as e:
            logger.exception("Error in PLANNING stage")
            state.fail_stage(StageName.PLANNING, str(e))
            state.skip_downstream_stages(StageName.PLANNING)
            return self._create_result(state, status="failed", error=str(e))

        # ------------------------------------------------------------------
        # Stage 3: ASAA (Spatial Allocation)
        # ------------------------------------------------------------------
        state.start_stage(StageName.ASAA)
        try:
            state.allocation_set = self.asaa_allocator.allocate(state.planning_spec)
            state.complete_stage(
                StageName.ASAA,
                metadata={"allocations_count": len(state.allocation_set.allocations)},
            )
        except Exception as e:
            logger.exception("Error in ASAA stage")
            state.fail_stage(StageName.ASAA, str(e))
            state.skip_downstream_stages(StageName.ASAA)
            return self._create_result(state, status="failed", error=str(e))

        # ------------------------------------------------------------------
        # Stage 4: ARCHITECTURAL_DESIGN (LLM Intent)
        # ------------------------------------------------------------------
        state.start_stage(StageName.ARCHITECTURAL_DESIGN)
        try:
            state.architectural_design_set = self.architectural_agent.design(
                planning_spec=state.planning_spec,
                allocation_set=state.allocation_set,
                requirements=state.requirements,
            )
            state.complete_stage(
                StageName.ARCHITECTURAL_DESIGN,
                metadata={"designs_count": len(state.architectural_design_set.designs)},
            )
        except Exception as e:
            logger.exception("Error in ARCHITECTURAL_DESIGN stage")
            state.fail_stage(StageName.ARCHITECTURAL_DESIGN, str(e))
            state.skip_downstream_stages(StageName.ARCHITECTURAL_DESIGN)
            return self._create_result(state, status="failed", error=str(e))

        # ------------------------------------------------------------------
        # Stage 5: GEOMETRY (Physical Construction)
        # ------------------------------------------------------------------
        state.start_stage(StageName.GEOMETRY)
        try:
            p_bound = None
            if state.requirements:
                if getattr(state.requirements, "plot_boundary", None):
                    p_bound = state.requirements.plot_boundary
                elif state.requirements.plot_shape:
                    p_bound = list(state.requirements.plot_shape)
                elif state.requirements.plot_dimensions:
                    w, d = state.requirements.plot_dimensions
                    p_bound = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]

            b_bound = getattr(state.requirements, "buildable_boundary", None)
            if not b_bound and p_bound and state.requirements:
                try:
                    from app.asaa.boundary import BuildableBoundaryCalculator
                    setbacks = state.requirements.setbacks or {}
                    b_obj = BuildableBoundaryCalculator.calculate(plot_polygon=p_bound, setbacks=setbacks)
                    b_bound = b_obj.polygon
                except Exception:
                    b_bound = None

            state.floor_plan_set = self.geometry_engine.construct(
                state.architectural_design_set,
                state.allocation_set,
                plot_boundary=p_bound,
                buildable_boundary=b_bound,
            )
            state.complete_stage(
                StageName.GEOMETRY,
                metadata={"floor_plans_count": len(state.floor_plan_set.floor_plans)},
            )
        except Exception as e:
            logger.exception("Error in GEOMETRY stage")
            state.fail_stage(StageName.GEOMETRY, str(e))
            state.skip_downstream_stages(StageName.GEOMETRY)
            return self._create_result(state, status="failed", error=str(e))

        # ------------------------------------------------------------------
        # Stage 6: VALIDATION (Independent Verification)
        # ------------------------------------------------------------------
        state.start_stage(StageName.VALIDATION)
        try:
            state.validation_report = self.validator.validate(
                state.floor_plan_set,
                requirements=state.requirements,
                planning_spec=state.planning_spec,
                allocation_set=state.allocation_set,
                architectural_design_set=state.architectural_design_set,
                plot_boundary=p_bound,
                buildable_boundary=b_bound,
            )
            state.floor_plan_set.validation_report = state.validation_report
            state.complete_stage(
                StageName.VALIDATION,
                metadata={
                    "overall_valid": state.validation_report.overall_valid,
                    "score": state.validation_report.overall_score,
                    "errors": state.validation_report.total_errors,
                },
            )
        except Exception as e:
            logger.exception("Error in VALIDATION stage")
            state.fail_stage(StageName.VALIDATION, str(e))
            state.skip_downstream_stages(StageName.VALIDATION)
            return self._create_result(state, status="failed", error=str(e))

        # ------------------------------------------------------------------
        # Stage 7: REFINEMENT (Validation-Driven Closed Loop)
        # ------------------------------------------------------------------
        state.start_stage(StageName.REFINEMENT)
        try:
            if not state.validation_report.overall_valid and cfg.enable_refinement:
                ref_res = self.refinement_loop.run(
                    initial_design=state.architectural_design_set,
                    allocation_set=state.allocation_set,
                    planning_spec=state.planning_spec,
                    initial_report=state.validation_report,
                    max_iterations=cfg.max_refinement_iterations,
                    requirements=state.requirements,
                    plot_boundary=p_bound,
                    buildable_boundary=b_bound,
                )
                state.refinement_result = ref_res

                # Sync refined design, geometry, and validation report directly from the loop
                if ref_res.final_design:
                    state.architectural_design_set = ref_res.final_design
                if ref_res.final_floor_plan_set:
                    state.floor_plan_set = ref_res.final_floor_plan_set
                if ref_res.final_report:
                    state.validation_report = ref_res.final_report
                    if state.floor_plan_set:
                        state.floor_plan_set.validation_report = ref_res.final_report

                status_val = ref_res.status.value if hasattr(ref_res.status, "value") else str(ref_res.status)
                state.complete_stage(
                    StageName.REFINEMENT,
                    metadata={
                        "refinement_status": status_val,
                        "iterations": ref_res.iteration,
                        "changes_count": len(ref_res.applied_changes),
                        "stop_reason": getattr(ref_res, "stop_reason", status_val),
                    },
                )
            else:
                state.complete_stage(
                    StageName.REFINEMENT,
                    metadata={"skipped": True, "reason": "Initial design valid or refinement disabled"},
                )
        except Exception as e:
            logger.exception("Error in REFINEMENT stage")
            state.fail_stage(StageName.REFINEMENT, str(e))
            # Continue to diversity / trace / export even if refinement hit an exception
            # using the pre-refinement geometry

        # ------------------------------------------------------------------
        # Stage 8: MULTI_DESIGN (Diversity & Alternatives)
        # ------------------------------------------------------------------
        state.start_stage(StageName.MULTI_DESIGN)
        try:
            if cfg.num_alternatives > 1:
                alt_set = self.diversity_generator.generate(
                    planning_spec=state.planning_spec,
                    allocation_set=state.allocation_set,
                    requirements=state.requirements,
                    num_alternatives=cfg.num_alternatives,
                    candidate_budget=cfg.candidate_budget,
                    minimum_diversity_distance=cfg.minimum_diversity_distance,
                    strategies=cfg.strategies,
                    max_refinement_iterations=cfg.max_refinement_iterations,
                    project_name=pname,
                )
                state.alternative_set = alt_set
                # If primary floor plan is in alternatives, ensure synced
                if alt_set.alternatives:
                    state.floor_plan_set = alt_set.alternatives[0].floor_plan_set or state.floor_plan_set
                    state.validation_report = alt_set.alternatives[0].validation_report or state.validation_report
            else:
                # Wrap primary floor plan neutrally as a single alternative
                primary_alt = DesignAlternative(
                    alternative_id=f"{pid}_alt_1",
                    index=1,
                    strategy="standard",
                    architectural_design=state.architectural_design_set,
                    floor_plan_set=state.floor_plan_set,
                    validation_report=state.validation_report,
                    refinement_result=state.refinement_result,
                    status=AlternativeStatus.VALIDATED if state.validation_report.overall_valid else AlternativeStatus.FAILED_VALIDATION,
                    design_rationale="Primary constructed design proposal",
                    characteristics=["Standard optimized layout"],
                )
                state.alternative_set = DesignAlternativeSet(
                    project_name=pname,
                    requested_count=1,
                    candidates_generated=1,
                    alternatives=[primary_alt],
                )

            state.complete_stage(
                StageName.MULTI_DESIGN,
                metadata={"alternatives_count": len(state.alternative_set.alternatives)},
            )
        except Exception as e:
            logger.exception("Error in MULTI_DESIGN stage")
            state.fail_stage(StageName.MULTI_DESIGN, str(e))

        # ------------------------------------------------------------------
        # Stage 9: EXPLAINABILITY (Decision Trace)
        # ------------------------------------------------------------------
        state.start_stage(StageName.EXPLAINABILITY)
        try:
            trace = self.trace_builder.build(
                requirements=state.requirements,
                planning_spec=state.planning_spec,
                allocation_set=state.allocation_set,
                architectural_design_set=state.architectural_design_set,
                geometry_set=state.floor_plan_set,
                validation_report=state.validation_report,
                refinement_result=state.refinement_result,
                alternative_set=state.alternative_set,
                project_name=pname,
            )
            state.decision_trace = trace
            state.complete_stage(
                StageName.EXPLAINABILITY,
                metadata={"events_count": len(trace.stages), "trace_id": trace.trace_id},
            )
        except Exception as e:
            logger.exception("Error in EXPLAINABILITY stage")
            state.fail_stage(StageName.EXPLAINABILITY, str(e))

        # ------------------------------------------------------------------
        # Stage 10: EXPORT (Rendering, Reports, Bundles)
        # ------------------------------------------------------------------
        state.start_stage(StageName.EXPORT)
        try:
            if cfg.enable_exports:
                bundle_path = export_project_bundle(
                    output_dir=cfg.output_dir,
                    project_id=pid,
                    project_name=pname,
                    requirements=state.requirements,
                    planning_spec=state.planning_spec,
                    allocation_set=state.allocation_set,
                    architectural_design_set=state.architectural_design_set,
                    floor_plan_set=state.floor_plan_set,
                    validation_report=state.validation_report,
                    refinement_result=state.refinement_result,
                    alternative_set=state.alternative_set,
                    decision_trace=state.decision_trace,
                    render_images=cfg.enable_rendering,
                    create_zip=cfg.create_zip,
                    render_options=cfg.render_options,
                )
                state.export_bundle_path = str(bundle_path)
                f_count = len(state.requirements.floors) if state.requirements and state.requirements.floors else 1
                alt_count = len(state.alternative_set.alternatives) if state.alternative_set else 1
                state.export_integrity_report = verify_export_integrity(
                    bundle_path,
                    expected_floors=f_count,
                    expected_alternatives=alt_count,
                    check_images=cfg.enable_rendering,
                    check_trace=state.decision_trace is not None,
                    check_dxf=True,
                )
                state.complete_stage(
                    StageName.EXPORT,
                    metadata={"bundle_path": str(bundle_path), "integrity_valid": state.export_integrity_report.is_valid},
                )
            else:
                state.complete_stage(
                    StageName.EXPORT,
                    metadata={"skipped": True, "reason": "Exports disabled by configuration"},
                )
        except Exception as e:
            logger.exception("Error in EXPORT stage")
            state.fail_stage(StageName.EXPORT, str(e))

        # Determine overall execution status based on final validator authority
        final_status = "completed"
        if cfg.enable_refinement and state.validation_report and not state.validation_report.overall_valid:
            if state.refinement_result and state.refinement_result.status == RefinementStatus.INFEASIBLE_UNDER_CONSTRAINTS:
                final_status = "failed"
            else:
                final_status = "unresolved"

        return self._create_result(state, status=final_status)

    def _create_result(
        self,
        state: PipelineState,
        status: str,
        error: Optional[str] = None,
        missing_fields: Optional[list[str]] = None,
        missing_floors: Optional[list[int]] = None,
        clarification_questions: Optional[list[str]] = None,
    ) -> PipelineResult:
        """Assemble a complete PipelineResult from current state."""
        return PipelineResult(
            project_id=state.project_id,
            project_name=state.project_name,
            status=status,
            requirements=state.requirements,
            completeness_result=state.completeness_result,
            planning_spec=state.planning_spec,
            allocation_set=state.allocation_set,
            architectural_design_set=state.architectural_design_set,
            floor_plan_set=state.floor_plan_set,
            validation_report=state.validation_report,
            refinement_result=state.refinement_result,
            alternative_set=state.alternative_set,
            decision_trace=state.decision_trace,
            export_bundle_path=state.export_bundle_path,
            export_integrity_report=state.export_integrity_report,
            stage_records={k.value: v for k, v in state.stage_records.items()},
            error_message=error,
            missing_fields=missing_fields or [],
            missing_floors=missing_floors or [],
            clarification_questions=clarification_questions or [],
        )


def create_default_orchestrator(config: Optional[OrchestrationConfig] = None) -> PlanForgeOrchestrator:
    """Factory creating a standard PlanForgeOrchestrator instance."""
    return PlanForgeOrchestrator()
