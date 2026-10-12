"""Tool registration and factory for PlanForge Agentic Architecture.

Provides the authoritative registry of approved tools that agents can invoke.
Every tool declares:
- Input JSON schema
- Output properties
- Side effects
- Artifact dependencies (reads) and outputs (writes)
- The owning agent
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.agentic.state import Finding, ProjectState
from app.agentic.tools import ToolRegistry, ToolResult, ToolSpec
from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.diversity_agent import MultiDesignGenerator
from app.agents.planning_agent import PlanningAgent
from app.agents.refinement_agent import RefinementLoop
from app.agents.requirement_agent import RequirementAgent
from app.agents.requirement_agent.completeness_gate import CompletenessGate
from app.agents.validation_agent import ValidationAgent
from app.asaa.allocator import ASAAAllocator
from app.asaa.boundary import BuildableBoundaryCalculator
from app.asaa.exceptions import InfeasibleAllocationError
from app.export.bundle_exporter import BundleExporter, export_project_bundle
from app.geometry.engine import GeometryEngine
from app.models.requirements import Requirements
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)

Point2D = Tuple[float, float]


def _extract_boundaries(requirements: Optional[Requirements]) -> Tuple[Optional[List[Point2D]], Optional[List[Point2D]]]:
    p_bound: Optional[List[Point2D]] = None
    b_bound: Optional[List[Point2D]] = None
    if requirements:
        if getattr(requirements, "plot_boundary", None):
            p_bound = list(requirements.plot_boundary)
        elif requirements.plot_shape:
            p_bound = list(requirements.plot_shape)
        elif requirements.plot_dimensions:
            w, d = requirements.plot_dimensions
            p_bound = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]

        b_bound = getattr(requirements, "buildable_boundary", None)
        if not b_bound and p_bound:
            try:
                setbacks = requirements.setbacks or {}
                b_obj = BuildableBoundaryCalculator.calculate(plot_polygon=p_bound, setbacks=setbacks)
                b_bound = b_obj.polygon
            except Exception:
                b_bound = None
    return p_bound, b_bound


def create_default_tool_registry(
    requirement_agent: Optional[RequirementAgent] = None,
    planning_agent: Optional[PlanningAgent] = None,
    asaa_allocator: Optional[ASAAAllocator] = None,
    architectural_agent: Optional[ArchitecturalAgent] = None,
    geometry_engine: Optional[GeometryEngine] = None,
    validation_agent: Optional[ValidationAgent] = None,
    refinement_loop: Optional[RefinementLoop] = None,
    diversity_generator: Optional[MultiDesignGenerator] = None,
    exporter: Optional[BundleExporter] = None,
) -> ToolRegistry:
    """Build and populate the standard PlanForge tool registry."""
    req_agent = requirement_agent or RequirementAgent()
    plan_agent = planning_agent or PlanningAgent()
    allocator = asaa_allocator or ASAAAllocator(seed=42)
    arch_agent = architectural_agent or ArchitecturalAgent()
    geom_engine = geometry_engine or GeometryEngine()
    val_agent = validation_agent or ValidationAgent()
    ref_loop = refinement_loop or RefinementLoop(geometry_engine=geom_engine, validator=val_agent.validator)
    div_gen = diversity_generator or MultiDesignGenerator(
        architectural_agent=arch_agent,
        refinement_loop=ref_loop,
        geometry_engine=geom_engine,
        validator=val_agent.validator,
    )
    bundle_exp = exporter or BundleExporter()

    registry = ToolRegistry()

    # -----------------------------------------------------------------------
    # Tool 1: parse_requirements
    # -----------------------------------------------------------------------
    def handle_parse_requirements(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        raw_brief = args.get("raw_brief") or state.inputs.get("raw_brief") or state.goal
        project_name = args.get("project_name") or state.inputs.get("project_name") or "PlanForge Project"
        req_override = state.inputs.get("requirements")

        if req_override is not None:
            requirements = req_override
            gate = CompletenessGate()
            comp_res = gate.check(requirements)
        elif raw_brief:
            pipe_res = req_agent.process(raw_brief, project_name=project_name)
            requirements = pipe_res.requirements
            comp_res = pipe_res.completeness
        else:
            return ToolResult.failure("MissingInput", "Neither raw_brief nor requirements provided.", outcome="needs_input")

        if comp_res and not comp_res.can_proceed:
            questions = list(comp_res.clarification_questions)
            missing = list(comp_res.missing_fields)
            if comp_res.missing_floors:
                missing.append(f"floors_{comp_res.missing_floors}")
            return ToolResult(
                ok=False,
                outcome="needs_input",
                summary=f"Requirements incomplete: {', '.join(missing)}",
                questions=questions,
                data={"missing_fields": missing, "can_proceed": False},
                artifacts={"requirements": requirements},
            )

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Parsed {requirements.total_rooms()} rooms across {len(requirements.floors or [1])} floor(s).",
            data={
                "project_name": requirements.project_name,
                "total_rooms": requirements.total_rooms(),
                "floors_count": len(requirements.floors or [1]),
            },
            artifacts={"requirements": requirements},
            facts={
                "floors_count": len(requirements.floors or [1]),
                "total_rooms": requirements.total_rooms(),
                "plot_shape": requirements.plot_shape,
            },
        )

    registry.register(
        ToolSpec(
            name="parse_requirements",
            handler=handle_parse_requirements,
            description="Parse and normalize natural language architectural brief into structured requirements.",
            agent="requirement_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "raw_brief": {"type": "string"},
                    "project_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"total_rooms": {"type": "integer"}, "floors_count": {"type": "integer"}}},
            side_effects=("parses_raw_brief", "validates_completeness"),
            reads=(),
            writes=("requirements",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 2: check_feasibility
    # -----------------------------------------------------------------------
    def handle_check_feasibility(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        req: Requirements = state.get_artifact("requirements")
        if not req:
            return ToolResult.failure("PreconditionFailed", "Requirements not found in artifacts.")

        p_bound, b_bound = _extract_boundaries(req)
        if not p_bound:
            return ToolResult.failure("NoPlotBoundary", "Cannot check feasibility without plot boundary.")

        try:
            from shapely.geometry import Polygon
            b_poly = Polygon(b_bound) if b_bound else Polygon(p_bound)
            buildable_area = b_poly.area
        except Exception as e:
            return ToolResult.failure("GeometryError", f"Failed to compute buildable area: {e}")

        # Check total minimum room area against buildable area per floor
        floor_deficits: List[Dict[str, Any]] = []
        is_multi_floor = len(req.floors or []) > 1

        for f in req.floors or []:
            req_min_sum = 0.0
            rooms_list = getattr(f, "room_requirements", None) or getattr(f, "rooms", [])
            for r in rooms_list:
                min_a = getattr(r, "min_area_sqm", None) or (r.target_area_sqm * 0.8 if getattr(r, "target_area_sqm", None) else 10.0)
                count = getattr(r, "min_count", None) or getattr(r, "count", 1) or 1
                req_min_sum += min_a * count
            stair_allowance = 8.0 if is_multi_floor else 0.0
            available = buildable_area - stair_allowance
            if req_min_sum > available:
                deficit = req_min_sum - available
                floor_deficits.append({
                    "floor": f.floor_number,
                    "required_min_sqm": round(req_min_sum, 1),
                    "available_sqm": round(available, 1),
                    "deficit_sqm": round(deficit, 1),
                })

        if floor_deficits:
            deficit_info = floor_deficits[0]
            summary_msg = (
                f"Infeasible room program: Floor {deficit_info['floor']} requires {deficit_info['required_min_sqm']} m² "
                f"which exceeds available {deficit_info['available_sqm']} m² by {deficit_info['deficit_sqm']} m²."
            )
            return ToolResult(
                ok=False,
                outcome="infeasible",
                summary=summary_msg,
                infeasibility={
                    "reason": "area_deficit",
                    "deficits": floor_deficits,
                    "buildable_area_sqm": round(buildable_area, 1),
                },
                facts={"feasibility_checked": True, "feasible": False, "deficits": floor_deficits},
            )

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Feasibility verified: Buildable area {round(buildable_area, 1)} m² accommodates requirements.",
            data={"buildable_area_sqm": round(buildable_area, 1), "feasible": True},
            facts={"feasibility_checked": True, "feasible": True, "buildable_area_sqm": round(buildable_area, 1)},
        )

    registry.register(
        ToolSpec(
            name="check_feasibility",
            handler=handle_check_feasibility,
            description="Verify physical plot capacity and room area budget before allocation.",
            agent="planning_agent",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"properties": {"feasible": {"type": "boolean"}, "buildable_area_sqm": {"type": "number"}}},
            side_effects=("calculates_envelope_budget",),
            reads=("requirements",),
            writes=(),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 3: plan_spatial_program
    # -----------------------------------------------------------------------
    def handle_plan_spatial_program(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        req: Requirements = state.get_artifact("requirements")
        strategy = args.get("strategy") or state.strategy.get("planning_strategy") or "balanced"

        try:
            planning_spec = plan_agent.plan(req, strategy=strategy)
        except Exception as e:
            logger.exception("Error in planning agent")
            return ToolResult.failure("PlanningError", str(e))

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Generated planning specification ({strategy} strategy) with {len(planning_spec.floors)} floor spec(s).",
            data={
                "floors_count": len(planning_spec.floors),
                "total_target_area": round(planning_spec.total_target_area(), 1),
                "strategy": strategy,
            },
            artifacts={"planning_spec": planning_spec},
            strategy={"planning_strategy": strategy},
            facts={"programmed_floors": len(planning_spec.floors)},
        )

    registry.register(
        ToolSpec(
            name="plan_spatial_program",
            handler=handle_plan_spatial_program,
            description="Synthesize requirements into strategic planning specification with zoning and adjacency graph.",
            agent="planning_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "strategy": {"type": "string", "enum": ["balanced", "compact", "open_plan", "circulation_prioritized"]},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"floors_count": {"type": "integer"}, "strategy": {"type": "string"}}},
            side_effects=("constructs_planning_spec",),
            reads=("requirements",),
            writes=("planning_spec",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 4: allocate_spatial_regions
    # -----------------------------------------------------------------------
    def handle_allocate_spatial_regions(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        spec = state.get_artifact("planning_spec")
        seed = args.get("seed", 42)
        n_cands = args.get("num_candidates", 1)

        try:
            alloc_set = allocator.allocate(spec, seed=seed, num_candidates=n_cands)
        except InfeasibleAllocationError as e:
            return ToolResult(
                ok=False,
                outcome="infeasible",
                summary=f"ASAA Allocation infeasible: {e}",
                infeasibility={"reason": "asaa_infeasible", "error": str(e)},
                error_type="InfeasibleAllocationError",
                error_message=str(e),
            )
        except Exception as e:
            logger.exception("Error in ASAA allocation")
            return ToolResult.failure("AllocationError", str(e))

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Allocated spatial regions for {len(alloc_set.allocations)} floor(s) using ASAA.",
            data={"allocations_count": len(alloc_set.allocations)},
            artifacts={"allocation_set": alloc_set},
            facts={"allocations_count": len(alloc_set.allocations)},
        )

    registry.register(
        ToolSpec(
            name="allocate_spatial_regions",
            handler=handle_allocate_spatial_regions,
            description="Run Adaptive Space Allocation Algorithm (ASAA) to partition buildable envelope into continuous regions.",
            agent="asaa_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "strategy": {"type": "string"},
                    "seed": {"type": "integer"},
                    "num_candidates": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"allocations_count": {"type": "integer"}}},
            side_effects=("simulated_annealing_allocation",),
            reads=("planning_spec",),
            writes=("allocation_set",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 5: design_architecture
    # -----------------------------------------------------------------------
    def handle_design_architecture(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        planning_spec = state.get_artifact("planning_spec")
        allocation_set = state.get_artifact("allocation_set")
        requirements = state.get_artifact("requirements")
        strategy = args.get("strategy") or "standard"

        try:
            arch_set = arch_agent.design(
                planning_spec=planning_spec,
                allocation_set=allocation_set,
                requirements=requirements,
                strategy=strategy,
            )
        except Exception as e:
            logger.exception("Error in architectural design agent")
            return ToolResult.failure("ArchitecturalDesignError", str(e))

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Generated architectural designs for {len(arch_set.designs)} floor(s).",
            data={"designs_count": len(arch_set.designs), "strategy": strategy},
            artifacts={"architectural_design_set": arch_set},
        )

    registry.register(
        ToolSpec(
            name="design_architecture",
            handler=handle_design_architecture,
            description="Translate allocated spatial regions into architectural room layouts, doors, and windows.",
            agent="architectural_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "strategy": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"designs_count": {"type": "integer"}}},
            side_effects=("generates_architectural_intent",),
            reads=("planning_spec", "allocation_set", "requirements"),
            writes=("architectural_design_set",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 6: construct_geometry
    # -----------------------------------------------------------------------
    def handle_construct_geometry(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        arch_set = state.get_artifact("architectural_design_set")
        alloc_set = state.get_artifact("allocation_set")
        req = state.get_artifact("requirements")
        p_bound, b_bound = _extract_boundaries(req)

        try:
            fp_set = geom_engine.construct(
                design_set=arch_set,
                allocation_set=alloc_set,
                plot_boundary=p_bound,
                buildable_boundary=b_bound,
            )
        except Exception as e:
            logger.exception("Error in geometry engine")
            return ToolResult.failure("GeometryConstructionError", str(e))

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Constructed physical geometry for {len(fp_set.floor_plans)} floor plan(s).",
            data={"floor_plans_count": len(fp_set.floor_plans)},
            artifacts={"floor_plan_set": fp_set},
        )

    registry.register(
        ToolSpec(
            name="construct_geometry",
            handler=handle_construct_geometry,
            description="Synthesize exact Shapely 2D room polygons, walls, doors, and windows.",
            agent="geometry_engine",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"properties": {"floor_plans_count": {"type": "integer"}}},
            side_effects=("constructs_authoritative_geometry",),
            reads=("architectural_design_set", "allocation_set"),
            writes=("floor_plan_set",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 7: validate_design
    # -----------------------------------------------------------------------
    def handle_validate_design(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        fp_set = state.get_artifact("floor_plan_set")
        req = state.get_artifact("requirements")
        spec = state.get_artifact("planning_spec")
        alloc = state.get_artifact("allocation_set")
        arch = state.get_artifact("architectural_design_set")
        p_bound, b_bound = _extract_boundaries(req)

        analysis = val_agent.validate(
            floor_plan_set=fp_set,
            requirements=req,
            planning_spec=spec,
            allocation_set=alloc,
            architectural_design_set=arch,
            plot_boundary=p_bound,
            buildable_boundary=b_bound,
            iteration=state.step,
        )

        fp_set.validation_report = analysis.report

        # Stamp findings onto state
        state.apply_findings(analysis.findings, scope_keys=("floor_plan_set",))

        summary_msg = (
            f"Validation score: {analysis.score:.1f}/100. "
            f"Errors: {analysis.hard_error_count}, Warnings: {analysis.warning_count}."
        )

        return ToolResult(
            ok=analysis.is_valid,
            outcome="ok" if analysis.is_valid else "has_issues",
            summary=summary_msg,
            findings=analysis.findings,
            data=analysis.to_dict(),
            facts={
                "overall_valid": analysis.is_valid,
                "validation_score": analysis.score,
                "hard_error_count": analysis.hard_error_count,
                "warning_count": analysis.warning_count,
            },
        )

    registry.register(
        ToolSpec(
            name="validate_design",
            handler=handle_validate_design,
            description="Run independent deterministic verification across overlap, boundary, dimension, door, window, staircase, and circulation checks.",
            agent="validation_agent",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "properties": {
                    "is_valid": {"type": "boolean"},
                    "score": {"type": "number"},
                    "hard_error_count": {"type": "integer"},
                }
            },
            side_effects=("validates_physical_invariants",),
            reads=("floor_plan_set",),
            writes=(),
            validates=("floor_plan_set",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 8: refine_design
    # -----------------------------------------------------------------------
    def handle_refine_design(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        arch_set = state.get_artifact("architectural_design_set")
        alloc_set = state.get_artifact("allocation_set")
        spec = state.get_artifact("planning_spec")
        req = state.get_artifact("requirements")
        fp_set = state.get_artifact("floor_plan_set")
        p_bound, b_bound = _extract_boundaries(req)
        max_iters = args.get("max_iterations", 3)

        curr_report = getattr(fp_set, "validation_report", None)

        try:
            ref_res = ref_loop.run(
                initial_design=arch_set,
                allocation_set=alloc_set,
                requirements=req,
                planning_spec=spec,
                plot_boundary=p_bound,
                buildable_boundary=b_bound,
                initial_report=curr_report,
                max_iterations=max_iters,
            )
        except Exception as e:
            logger.exception("Error in refinement loop")
            return ToolResult.failure("RefinementError", str(e))

        artifacts: Dict[str, Any] = {}
        if ref_res.final_design:
            artifacts["architectural_design_set"] = ref_res.final_design
        if ref_res.final_floor_plan_set:
            artifacts["floor_plan_set"] = ref_res.final_floor_plan_set
            if ref_res.final_report:
                ref_res.final_floor_plan_set.validation_report = ref_res.final_report

        status_str = ref_res.status.value if hasattr(ref_res.status, "value") else str(ref_res.status)
        is_improved = ref_res.is_successful or (ref_res.final_report and ref_res.final_report.overall_valid)

        return ToolResult(
            ok=is_improved,
            outcome="ok" if is_improved else "no_effect",
            summary=f"Refinement status: {status_str} after {ref_res.iteration} iteration(s), {len(ref_res.applied_changes)} change(s).",
            data={
                "status": status_str,
                "iterations": ref_res.iteration,
                "changes_count": len(ref_res.applied_changes),
            },
            artifacts=artifacts,
            facts={"refinement_status": status_str, "changes_applied": len(ref_res.applied_changes)},
        )

    registry.register(
        ToolSpec(
            name="refine_design",
            handler=handle_refine_design,
            description="Execute iterative validation-driven refinement to resolve door, window, and boundary issues.",
            agent="refinement_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "max_iterations": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"status": {"type": "string"}, "changes_count": {"type": "integer"}}},
            side_effects=("iterative_design_correction",),
            reads=("architectural_design_set", "allocation_set"),
            writes=("architectural_design_set", "floor_plan_set"),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 9: generate_alternatives
    # -----------------------------------------------------------------------
    def handle_generate_alternatives(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        spec = state.get_artifact("planning_spec")
        alloc = state.get_artifact("allocation_set")
        req = state.get_artifact("requirements")
        n_alts = args.get("num_alternatives", 3)

        try:
            alt_set = div_gen.generate(
                planning_spec=spec,
                allocation_set=alloc,
                requirements=req,
                num_alternatives=n_alts,
            )
        except Exception as e:
            logger.exception("Error generating alternatives")
            return ToolResult.failure("DiversityGenerationError", str(e))

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Generated {len(alt_set.alternatives)} diverse design alternative(s).",
            data={"alternatives_count": len(alt_set.alternatives)},
            artifacts={"alternative_set": alt_set},
            facts={"alternatives_count": len(alt_set.alternatives)},
        )

    registry.register(
        ToolSpec(
            name="generate_alternatives",
            handler=handle_generate_alternatives,
            description="Explore candidate layout alternatives across spatial strategies.",
            agent="diversity_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "num_alternatives": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"alternatives_count": {"type": "integer"}}},
            side_effects=("generates_diverse_alternatives",),
            reads=("planning_spec", "allocation_set", "requirements"),
            writes=("alternative_set",),
        )
    )

    # -----------------------------------------------------------------------
    # Tool 10: export_bundle
    # -----------------------------------------------------------------------
    def handle_export_bundle(state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        out_dir = args.get("output_dir", "outputs")
        pid = state.project_id
        pname = state.goal or "PlanForge Project"
        req = state.get_artifact("requirements")
        spec = state.get_artifact("planning_spec")
        alloc = state.get_artifact("allocation_set")
        arch = state.get_artifact("architectural_design_set")
        fp = state.get_artifact("floor_plan_set")
        alts = state.get_artifact("alternative_set")
        render_imgs = args.get("enable_rendering", True)
        zip_arch = args.get("create_zip", True)

        val_rep = getattr(fp, "validation_report", None) if fp else None

        try:
            bundle_path = export_project_bundle(
                output_dir=out_dir,
                project_id=pid,
                project_name=pname,
                requirements=req,
                planning_spec=spec,
                allocation_set=alloc,
                architectural_design_set=arch,
                floor_plan_set=fp,
                validation_report=val_rep,
                alternative_set=alts,
                render_images=render_imgs,
                create_zip=zip_arch,
            )
        except Exception as e:
            logger.exception("Error exporting project bundle")
            return ToolResult.failure("ExportError", str(e))

        return ToolResult(
            ok=True,
            outcome="ok",
            summary=f"Successfully exported project bundle to {bundle_path}",
            data={"bundle_path": str(bundle_path)},
            facts={"export_bundle_path": str(bundle_path)},
        )

    registry.register(
        ToolSpec(
            name="export_bundle",
            handler=handle_export_bundle,
            description="Export verified CAD DXF files, SVG/PNG renderings, and compliance reports.",
            agent="export_agent",
            input_schema={
                "type": "object",
                "properties": {
                    "output_dir": {"type": "string"},
                    "enable_rendering": {"type": "boolean"},
                    "create_zip": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            output_schema={"properties": {"bundle_path": {"type": "string"}}},
            side_effects=("writes_bundle_to_disk",),
            reads=("floor_plan_set",),
            writes=(),
        )
    )

    return registry
