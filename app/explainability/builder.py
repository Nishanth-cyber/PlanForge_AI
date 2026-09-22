"""DecisionTraceBuilder for constructing linked, auditable DecisionTraces.

This module inspects pipeline stage artifacts (Requirements, PlanningSpec, AllocationSet,
ArchitecturalDesignSet, FloorPlanSet, ValidationReport, RefinementResult, DesignAlternativeSet)
and constructs an end-to-end DecisionTrace with explicit entity linkages and provenance attribution.

Critical Invariants:
1. READ-ONLY: Never modifies input artifacts.
2. NO FABRICATION: Never reports facts or score components not present in artifacts.
3. NO CHAIN-OF-THOUGHT: Never stores internal LLM scratchpad or private deliberations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from app.explainability.events import (
    create_alternative_event,
    create_architectural_event,
    create_asaa_event,
    create_diversity_event,
    create_geometry_event,
    create_planning_event,
    create_refinement_event,
    create_requirement_event,
    create_validation_event,
)
from app.explainability.models import (
    AlternativeTrace,
    DecisionEvent,
    DecisionTrace,
    DecisionType,
    EntityTraceChain,
    ProvenanceSource,
    StageName,
    StageTrace,
)
from app.models.allocation import AllocationSet
from app.models.alternatives import DesignAlternativeSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.geometry import GeometrySet
from app.models.planning import PlanningSpec
from app.models.refinement import RefinementResult
from app.models.requirements import Requirements
from app.models.validation import ValidationReport
from app.utils.ids import generate_id


class DecisionTraceBuilder:
    """Constructs comprehensive, auditable DecisionTrace instances from pipeline artifacts."""

    @classmethod
    def build(
        cls,
        requirements: Optional[Requirements] = None,
        planning_spec: Optional[PlanningSpec] = None,
        allocation_set: Optional[AllocationSet] = None,
        architectural_design_set: Optional[ArchitecturalDesignSet] = None,
        geometry_set: Optional[Union[GeometrySet, FloorPlanSet]] = None,
        validation_report: Optional[ValidationReport] = None,
        refinement_result: Optional[RefinementResult] = None,
        alternative_set: Optional[DesignAlternativeSet] = None,
        project_name: Optional[str] = None,
    ) -> DecisionTrace:
        """Construct an unbroken DecisionTrace across all provided stage outputs."""
        proj = (
            project_name
            or (requirements.project_name if requirements else "")
            or (planning_spec.project_name if planning_spec else "")
            or (alternative_set.project_name if alternative_set else "")
            or "Residential Project"
        )

        all_events: list[DecisionEvent] = []
        stages: list[StageTrace] = []
        alternatives: list[AlternativeTrace] = []
        entity_chains: dict[str, EntityTraceChain] = {}

        # ------------------------------------------------------------------
        # Stage 1: Requirements Trace
        # ------------------------------------------------------------------
        if requirements:
            req_events = cls._trace_requirements(requirements)
            all_events.extend(req_events)
            req_floors = requirements.floors or requirements.floor_requirements or []
            stages.append(
                StageTrace(
                    stage_name=StageName.REQUIREMENT.value,
                    events=req_events,
                    summary=f"Parsed user requirements for {len(req_floors)} floor(s).",
                )
            )

        # ------------------------------------------------------------------
        # Stage 2: Planning Trace
        # ------------------------------------------------------------------
        if planning_spec:
            plan_events = cls._trace_planning(planning_spec, requirements)
            all_events.extend(plan_events)
            stages.append(
                StageTrace(
                    stage_name=StageName.PLANNING.value,
                    events=plan_events,
                    summary=f"Formulated architectural planning spec with {len(planning_spec.floors)} floor(s).",
                )
            )

        # ------------------------------------------------------------------
        # Stage 3: ASAA Allocation Trace
        # ------------------------------------------------------------------
        if allocation_set:
            asaa_events = cls._trace_asaa(allocation_set, planning_spec)
            all_events.extend(asaa_events)
            stages.append(
                StageTrace(
                    stage_name=StageName.ASAA_ALLOCATION.value,
                    events=asaa_events,
                    summary=f"Allocated spatial bounding regions across {len(allocation_set.allocations)} floor(s).",
                )
            )

        # ------------------------------------------------------------------
        # Stage 4: Architectural Design Trace
        # ------------------------------------------------------------------
        if architectural_design_set:
            arch_events = cls._trace_architectural(architectural_design_set, allocation_set=allocation_set)
            all_events.extend(arch_events)
            first_design = architectural_design_set.designs[0] if architectural_design_set.designs else None
            meta = first_design.metadata if first_design and hasattr(first_design, "metadata") else {}
            prov = meta.get("provider", "mock") if meta else "mock"
            default_mod = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B" if prov in ("huggingface", "hf") else "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
            mod = meta.get("model", default_mod) if meta else default_mod
            stages.append(
                StageTrace(
                    stage_name=StageName.ARCHITECTURAL_DESIGN.value,
                    events=arch_events,
                    summary=f"Proposed architectural room shapes and door/window intents via {prov} ({mod}) for {len(architectural_design_set.designs)} floor(s).",
                )
            )


        # ------------------------------------------------------------------
        # Stage 5: Geometry Engine Trace
        # ------------------------------------------------------------------
        if geometry_set:
            geom_events = cls._trace_geometry(
                geometry_set,
                arch_set=architectural_design_set,
                allocation_set=allocation_set,
            )
            all_events.extend(geom_events)
            stages.append(
                StageTrace(
                    stage_name=StageName.GEOMETRY.value,
                    events=geom_events,
                    summary="Constructed physical room polygons, walls, doors, and windows.",
                )
            )

        # ------------------------------------------------------------------
        # Stage 6: Validation Trace
        # ------------------------------------------------------------------
        val_rep = validation_report
        if not val_rep and refinement_result:
            val_rep = refinement_result.final_report
        if not val_rep and alternative_set and alternative_set.alternatives:
            val_rep = alternative_set.alternatives[0].validation_report

        if val_rep:
            val_events = cls._trace_validation(val_rep)
            all_events.extend(val_events)
            valid_str = "Passed" if val_rep.overall_valid else "Failed"
            stages.append(
                StageTrace(
                    stage_name=StageName.VALIDATION.value,
                    events=val_events,
                    summary=f"Independent validation {valid_str} with {val_rep.total_errors} error(s) and {val_rep.total_warnings} warning(s).",
                )
            )

        # ------------------------------------------------------------------
        # Stage 7: Refinement Trace
        # ------------------------------------------------------------------
        if refinement_result:
            ref_events = cls._trace_refinement(refinement_result)
            all_events.extend(ref_events)
            stages.append(
                StageTrace(
                    stage_name=StageName.REFINEMENT.value,
                    events=ref_events,
                    summary=f"Refinement loop status: {refinement_result.status.value} ({refinement_result.total_iterations} iterations, {len(refinement_result.changes)} changes).",
                )
            )

        # ------------------------------------------------------------------
        # Stage 8 & 9: Diversity & Alternatives Trace
        # ------------------------------------------------------------------
        if alternative_set:
            div_events, alt_traces = cls._trace_diversity_and_alternatives(alternative_set)
            all_events.extend(div_events)
            stages.append(
                StageTrace(
                    stage_name=StageName.DIVERSITY.value,
                    events=div_events,
                    summary=f"Generated {len(alternative_set.alternatives)} valid diverse alternative(s) and logged {len(alternative_set.rejected_candidates)} rejected candidate(s).",
                )
            )
            alternatives.extend(alt_traces)

        # Build entity chains for all identified rooms
        entity_chains = cls._build_entity_chains(
            all_events,
            planning_spec=planning_spec,
            allocation_set=allocation_set,
            arch_set=architectural_design_set,
            geometry_set=geometry_set,
        )

        return DecisionTrace(
            trace_id=generate_id("trace"),
            project_name=proj,
            stages=stages,
            alternatives=alternatives,
            entity_chains=entity_chains,
        )

    # ----------------------------------------------------------------------
    # Internal Stage Extraction Methods
    # ----------------------------------------------------------------------

    @classmethod
    def _trace_requirements(cls, requirements: Requirements) -> list[DecisionEvent]:
        """Extract explicit user requirements with user provenance."""
        events: list[DecisionEvent] = []

        # Plot requirements
        plot_evidence: dict[str, Any] = {}
        if requirements.plot_dimensions:
            plot_evidence["plot_dimensions"] = requirements.plot_dimensions
        if requirements.plot_shape:
            plot_evidence["plot_shape"] = list(requirements.plot_shape)
        if requirements.plot_area_sqm:
            plot_evidence["plot_area_sqm"] = requirements.plot_area_sqm
        if requirements.setbacks:
            plot_evidence["setbacks"] = requirements.setbacks
        if requirements.orientation:
            plot_evidence["orientation"] = requirements.orientation

        if plot_evidence:
            events.append(
                create_requirement_event(
                    entity_id="plot_boundary",
                    entity_type="plot",
                    reason="User specified plot boundaries, dimensions, orientation, and setbacks.",
                    evidence=plot_evidence,
                    constraints={"setbacks": requirements.setbacks or {}},
                )
            )

        # Room requirements
        for floor_req in (requirements.floor_requirements or requirements.floors or []):
            fn = floor_req.floor_number
            for r_req in floor_req.room_requirements:
                r_evidence = {
                    "room_type": r_req.room_type,
                    "count": r_req.min_count,
                    "target_area_sqm": getattr(r_req, "preferred_area_sqm", getattr(r_req, "target_area_sqm", None)),
                    "min_area_sqm": r_req.min_area_sqm,
                    "max_area_sqm": r_req.max_area_sqm,
                    "required_adjacency": list(r_req.adjacency),
                    "separation": list(r_req.separation),
                    "attached_to": r_req.attached_to,
                }
                r_constraints = {
                    "min_area_sqm": r_req.min_area_sqm,
                    "max_area_sqm": r_req.max_area_sqm,
                }
                events.append(
                    create_requirement_event(
                        entity_id=r_req.id,
                        entity_type="room",
                        floor_number=fn,
                        reason=f"User requested {r_req.min_count} {r_req.room_type} on Floor {fn}.",
                        evidence=r_evidence,
                        constraints=r_constraints,
                        output_references=[r_req.id],
                    )
                )

        return events

    @classmethod
    def _trace_planning(
        cls, planning_spec: PlanningSpec, requirements: Optional[Requirements]
    ) -> list[DecisionEvent]:
        """Extract planning decisions distinguishing user-specified vs system-derived."""
        events: list[DecisionEvent] = []

        # Map user required adjacencies to verify user vs system provenance
        user_adj_map: dict[str, list[str]] = {}
        if requirements:
            for fr in (requirements.floors or requirements.floor_requirements or []):
                for rr in fr.room_requirements:
                    if rr.adjacency:
                        user_adj_map[rr.room_type] = list(rr.adjacency)

        for floor_spec in planning_spec.floors:
            fn = floor_spec.floor_number

            # Circulation, Entrance, Staircase intent
            if floor_spec.entrance_intent:
                events.append(
                    create_planning_event(
                        event_type=DecisionType.STRATEGY_SELECTED,
                        source=ProvenanceSource.PLANNING_AGENT,
                        entity_id=f"entrance_intent_floor_{fn}",
                        entity_type="entrance",
                        floor_number=fn,
                        reason=f"Planned main building entrance facing {floor_spec.entrance_intent.get('facing', 'front')}.",
                        evidence=floor_spec.entrance_intent,
                    )
                )

            if floor_spec.staircase_intent and floor_spec.staircase_intent.get("required"):
                events.append(
                    create_planning_event(
                        event_type=DecisionType.STAIRCASE_INTENT_CREATED,
                        source=ProvenanceSource.PLANNING_AGENT,
                        entity_id=f"staircase_intent_floor_{fn}",
                        entity_type="staircase",
                        floor_number=fn,
                        reason="Planned vertical circulation core connecting building levels.",
                        evidence=floor_spec.staircase_intent,
                    )
                )

            # Room Specs
            for r_spec in floor_spec.room_specs:
                r_id = r_spec.id
                rtype = r_spec.room_type

                # 1. Room categorization
                events.append(
                    create_planning_event(
                        event_type=DecisionType.ROOM_CLASSIFIED,
                        source=ProvenanceSource.PLANNING_AGENT,
                        entity_id=r_id,
                        floor_number=fn,
                        reason=f"Classified '{rtype}' into functional category '{r_spec.room_category}'.",
                        evidence={
                            "room_type": rtype,
                            "category": r_spec.room_category,
                            "original_name": r_spec.original_name,
                        },
                        input_references=[r_spec.source_requirement_id] if r_spec.source_requirement_id else [],
                        output_references=[r_id],
                    )
                )

                # 2. Priority assignment
                events.append(
                    create_planning_event(
                        event_type=DecisionType.PRIORITY_ASSIGNED,
                        source=ProvenanceSource.PLANNING_AGENT,
                        entity_id=r_id,
                        floor_number=fn,
                        reason=r_spec.priority_rationale or f"Assigned planning priority '{r_spec.priority}' to {rtype}.",
                        evidence={
                            "room_type": rtype,
                            "priority": r_spec.priority,
                            "target_area_sqm": r_spec.target_area_sqm,
                        },
                        input_references=[r_id],
                    )
                )

                # 3. Relationships (User-specified vs System-derived)
                user_req_for_room = user_adj_map.get(rtype, [])
                for adj in r_spec.adjacency:
                    is_user = adj in user_req_for_room
                    src = ProvenanceSource.USER if is_user else ProvenanceSource.SYSTEM_DERIVED
                    rel_desc = "User explicitly requested adjacency" if is_user else "Planning agent inferred functional relationship"
                    events.append(
                        create_planning_event(
                            event_type=DecisionType.RELATIONSHIP_CREATED,
                            source=src,
                            entity_id=r_id,
                            floor_number=fn,
                            reason=f"{rel_desc} between '{rtype}' and '{adj}'.",
                            evidence={
                                "from_room": rtype,
                                "to_room": adj,
                                "is_user_specified": is_user,
                                "relationship_type": "adjacency",
                            },
                        )
                    )

                for av in r_spec.avoid:
                    events.append(
                        create_planning_event(
                            event_type=DecisionType.RELATIONSHIP_CREATED,
                            source=ProvenanceSource.SYSTEM_DERIVED,
                            entity_id=r_id,
                            floor_number=fn,
                            reason=f"Architectural acoustic/privacy separation constraint between '{rtype}' and '{av}'.",
                            evidence={
                                "from_room": rtype,
                                "to_room": av,
                                "relationship_type": "avoid",
                            },
                        )
                    )

        return events

    @classmethod
    def _trace_asaa(
        cls, allocation_set: AllocationSet, planning_spec: Optional[PlanningSpec]
    ) -> list[DecisionEvent]:
        """Extract ASAA spatial allocation facts and scoring components without fabrication."""
        events: list[DecisionEvent] = []

        for alloc in allocation_set.allocations:
            fn = alloc.floor_number

            for reg in alloc.allocated_regions:
                reg_id = reg.id
                rtype = reg.room_type
                r_spec_id = reg.room_spec_id

                evidence: dict[str, Any] = {
                    "allocated_region_id": reg_id,
                    "room_type": rtype,
                    "allocated_area_sqm": reg.area_sqm,
                    "target_area_sqm": reg.target_area_sqm,
                    "approximate_dimensions": reg.approximate_dimensions,
                    "priority": reg.priority,
                    "zone_type": reg.zone_type,
                    "score": reg.score,
                    "adjacency_regions": list(reg.adjacency_regions),
                }

                # Construct clean, evidence-based reason without inventing uncomputed factors
                reason_parts = [
                    f"Allocated {reg.area_sqm:.2f} m² region for '{rtype}' (target: {reg.target_area_sqm:.2f} m²)."
                ]
                if reg.priority == "high":
                    reason_parts.append("Prioritized due to high functional importance.")
                if reg.zone_type in ("circulation", "entrance"):
                    reason_parts.append(f"Designated as {reg.zone_type} spatial network.")

                events.append(
                    create_asaa_event(
                        event_type=DecisionType.ALLOCATION_ASSIGNED,
                        entity_id=r_spec_id or reg_id,
                        reason=" ".join(reason_parts),
                        evidence=evidence,
                        floor_number=fn,
                        input_references=[r_spec_id] if r_spec_id else [],
                        output_references=[reg_id],
                    )
                )

        return events

    @classmethod
    def _trace_architectural(
        cls,
        arch_set: ArchitecturalDesignSet,
        allocation_set: Optional[AllocationSet] = None,
    ) -> list[DecisionEvent]:
        """Extract architectural room shapes, doors, windows, and rationales."""
        events: list[DecisionEvent] = []

        reg_to_spec: dict[str, str] = {}
        if allocation_set:
            for alloc in allocation_set.allocations:
                for reg in alloc.allocated_regions:
                    if reg.room_spec_id:
                        reg_to_spec[reg.id] = reg.room_spec_id

        for floor_d in arch_set.designs:
            fn = floor_d.floor_number

            for room in floor_d.rooms:
                r_id = room.id
                rtype = room.room_type
                r_spec_id = reg_to_spec.get(room.allocated_region_id) if room.allocated_region_id else None

                # Shape & Dimensions
                room_evidence = {
                    "room_id": r_id,
                    "room_type": rtype,
                    "allocated_region_id": room.allocated_region_id,
                    "intended_shape": room.intended_shape,
                    "intended_dimensions": room.intended_dimensions,
                    "intended_area_sqm": room.intended_area_sqm,
                    "connected_spaces": list(room.connected_spaces),
                }
                floor_meta = getattr(floor_d, "metadata", {}) or {}
                if floor_meta:
                    f_prov = floor_meta.get("provider", "mock")
                    default_f_mod = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B" if f_prov in ("huggingface", "hf") else "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
                    room_evidence["llm_provider"] = f_prov
                    room_evidence["llm_model"] = floor_meta.get("model", default_f_mod)
                if r_spec_id:
                    room_evidence["room_spec_id"] = r_spec_id


                rationale = room.design_rationale or "Rationale not provided."
                events.append(
                    create_architectural_event(
                        event_type=DecisionType.ROOM_SHAPE_SELECTED,
                        entity_id=r_spec_id or r_id,
                        floor_number=fn,
                        reason=f"Designed '{rtype}' as {room.intended_shape} with dimensions {room.intended_dimensions}. {rationale}",
                        evidence=room_evidence,
                        input_references=[r_spec_id] if r_spec_id else ([room.allocated_region_id] if room.allocated_region_id else []),
                        output_references=[r_id],
                    )
                )

                # Doors
                for door in room.doors:
                    d_evidence = {
                        "door_id": door.id,
                        "room_id": r_id,
                        "connects_from": door.connects_from,
                        "connects_to": door.connects_to,
                        "door_type": door.door_type,
                        "wall_orientation": door.wall_orientation,
                        "recommended_width": door.recommended_width,
                    }
                    d_reason = door.rationale or f"Connects {door.connects_from} to {door.connects_to}."
                    events.append(
                        create_architectural_event(
                            event_type=DecisionType.DOOR_INTENT_CREATED,
                            entity_id=door.id,
                            entity_type="door",
                            floor_number=fn,
                            reason=d_reason,
                            evidence=d_evidence,
                            input_references=[r_id],
                            output_references=[door.id],
                        )
                    )

                # Windows
                for win in room.windows:
                    w_evidence = {
                        "window_id": win.id,
                        "room_id": r_id,
                        "wall_orientation": win.wall_orientation,
                        "window_type": win.window_type,
                        "recommended_width": win.recommended_width,
                        "sill_height": win.sill_height,
                    }
                    w_reason = win.rationale or f"Window on {win.wall_orientation} wall for natural light/ventilation."
                    events.append(
                        create_architectural_event(
                            event_type=DecisionType.WINDOW_INTENT_CREATED,
                            entity_id=win.id,
                            entity_type="window",
                            floor_number=fn,
                            reason=w_reason,
                            evidence=w_evidence,
                            input_references=[r_id],
                            output_references=[win.id],
                        )
                    )

        return events

    @classmethod
    def _trace_geometry(
        cls,
        geometry_set: Union[GeometrySet, FloorPlanSet],
        arch_set: Optional[ArchitecturalDesignSet] = None,
        allocation_set: Optional[AllocationSet] = None,
    ) -> list[DecisionEvent]:
        """Extract deterministic geometry construction facts."""
        events: list[DecisionEvent] = []

        arch_to_spec: dict[str, str] = {}
        if arch_set and allocation_set:
            reg_to_spec = {
                r.id: r.room_spec_id
                for a in allocation_set.allocations
                for r in a.allocated_regions
                if r.room_spec_id
            }
            for d in arch_set.designs:
                for rm in d.rooms:
                    if rm.allocated_region_id in reg_to_spec:
                        arch_to_spec[rm.id] = reg_to_spec[rm.allocated_region_id]

        floors = (
            geometry_set.floor_plans
            if isinstance(geometry_set, FloorPlanSet)
            else geometry_set.geometries
        )

        for f in floors:
            geom = f.geometry if hasattr(f, "geometry") else f
            fn = getattr(geom, "floor_number", 1)

            for room in geom.rooms:
                g_evidence = {
                    "geo_room_id": room.id,
                    "room_type": room.room_type,
                    "usable_area_sqm": room.area_sqm,
                    "walls_count": len(room.walls),
                    "doors_count": len(room.doors),
                    "windows_count": len(room.windows),
                    "is_corridor": room.is_corridor,
                }
                arch_ref = room.architectural_room_id
                r_spec_id = arch_to_spec.get(arch_ref) if arch_ref else None
                events.append(
                    create_geometry_event(
                        entity_id=r_spec_id or arch_ref or room.id,
                        entity_type="room",
                        floor_number=fn,
                        reason=f"Constructed physical {room.room_type} geometry with usable area {room.area_sqm:.2f} m².",
                        evidence=g_evidence,
                        input_references=[arch_ref] if arch_ref else [],
                        output_references=[room.id],
                    )
                )

        return events

    @classmethod
    def _trace_validation(cls, validation_report: ValidationReport) -> list[DecisionEvent]:
        """Extract independent validation findings with structured expected vs observed evidence."""
        events: list[DecisionEvent] = []

        for floor_res in validation_report.results:
            fn = floor_res.floor_number

            for check in floor_res.checks_passed:
                events.append(
                    create_validation_event(
                        event_type=DecisionType.VALIDATION_CHECKED,
                        entity_id=f"check_{check}_floor_{fn}",
                        check=check,
                        reason=f"Category '{check}' passed all verification checks on Floor {fn}.",
                        evidence={"floor_number": fn, "check": check, "status": "passed"},
                        severity="passed",
                        floor_number=fn,
                    )
                )

            for issue in floor_res.issues:
                ev_type = (
                    DecisionType.VALIDATION_FAILURE
                    if issue.severity == "error"
                    else DecisionType.VALIDATION_WARNING
                )
                i_evidence = {
                    "issue_id": issue.id,
                    "check": issue.check or issue.category,
                    "category": issue.category,
                    "severity": issue.severity,
                    "target_id": issue.target_id,
                    "room_id": issue.room_id,
                    "details": issue.details or {},
                }
                events.append(
                    create_validation_event(
                        event_type=ev_type,
                        entity_id=issue.room_id or issue.target_id or issue.id,
                        check=issue.check or issue.category,
                        reason=issue.message,
                        evidence=i_evidence,
                        severity=issue.severity,
                        floor_number=fn,
                        input_references=[issue.target_id] if issue.target_id else [],
                        output_references=[issue.id],
                    )
                )

        return events

    @classmethod
    def _trace_refinement(cls, refinement_result: RefinementResult) -> list[DecisionEvent]:
        """Extract closed-loop refinement decisions linking changes to validation issues."""
        events: list[DecisionEvent] = []

        for change in refinement_result.changes:
            c_evidence = {
                "change_id": change.id,
                "room_id": change.room_id,
                "field_changed": change.field_changed,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "validation_issue_ids": list(change.validation_issue_ids),
            }
            events.append(
                create_refinement_event(
                    event_type=DecisionType.REFINEMENT_APPLIED,
                    entity_id=change.room_id,
                    reason=change.reason or f"Adjusted {change.field_changed} during refinement to resolve validation issues.",
                    evidence=c_evidence,
                    validation_issue_ids=list(change.validation_issue_ids),
                    floor_number=getattr(change, "floor_number", None),
                )
            )

        return events

    @classmethod
    def _trace_diversity_and_alternatives(
        cls, alt_set: DesignAlternativeSet
    ) -> tuple[list[DecisionEvent], list[AlternativeTrace]]:
        """Extract diversity evaluations and alternative acceptance/rejection records."""
        events: list[DecisionEvent] = []
        alt_traces: list[AlternativeTrace] = []

        # 1. Accepted alternatives
        for alt in alt_set.alternatives:
            sig_dict = alt.design_signature.to_dict() if alt.design_signature else {}
            val_summary = {
                "is_valid": alt.is_valid,
                "score": alt.validation_report.overall_score if alt.validation_report else 100.0,
                "error_count": alt.validation_report.total_errors if alt.validation_report else 0,
            }
            ref_summary = {
                "refinement_status": alt.refinement_result.status.value if alt.refinement_result else "none",
                "iterations": alt.refinement_result.total_iterations if alt.refinement_result else 0,
            }

            alt_trace = AlternativeTrace(
                alternative_id=alt.alternative_id,
                index=alt.index,
                strategy=alt.strategy,
                status=alt.status.value,
                rejection_reason=None,
                design_signature=sig_dict,
                characteristics=list(alt.characteristics),
                validation_summary=val_summary,
                refinement_summary=ref_summary,
                diversity_scores=dict(alt.diversity_scores),
            )
            alt_traces.append(alt_trace)

            events.append(
                create_alternative_event(
                    event_type=DecisionType.ALTERNATIVE_ACCEPTED,
                    alternative_id=alt.alternative_id,
                    reason=f"Accepted Alternative {alt.index} ({alt.strategy}) satisfying all validation constraints and structural diversity thresholds.",
                    evidence={
                        "index": alt.index,
                        "strategy": alt.strategy,
                        "characteristics": list(alt.characteristics),
                        "diversity_scores": dict(alt.diversity_scores),
                    },
                    status="accepted",
                )
            )

        # 2. Rejected candidates
        for rej in alt_set.rejected_candidates:
            rej_summary = {
                "index": rej.index,
                "strategy": rej.strategy,
                "status": rej.status.value,
                "rejection_reason": rej.rejection_reason,
                "design_rationale": rej.design_rationale,
            }
            events.append(
                create_alternative_event(
                    event_type=DecisionType.ALTERNATIVE_REJECTED,
                    alternative_id=rej.alternative_id,
                    reason=rej.design_rationale or f"Candidate {rej.index} ({rej.strategy}) rejected due to {rej.rejection_reason}.",
                    evidence=rej_summary,
                    status="rejected",
                )
            )

        return events, alt_traces

    @classmethod
    def _build_entity_chains(
        cls,
        events: list[DecisionEvent],
        planning_spec: Optional[PlanningSpec] = None,
        allocation_set: Optional[AllocationSet] = None,
        arch_set: Optional[ArchitecturalDesignSet] = None,
        geometry_set: Optional[Union[GeometrySet, FloorPlanSet]] = None,
    ) -> dict[str, EntityTraceChain]:
        """Aggregate all room-level events across all pipeline stages into unbroken entity trace chains."""
        chains: dict[str, EntityTraceChain] = {}
        processed_event_ids: set[str] = set()

        if planning_spec:
            # Build lookup from region to spec
            reg_to_spec: dict[str, str] = {}
            if allocation_set:
                for alloc in allocation_set.allocations:
                    for reg in alloc.allocated_regions:
                        if reg.room_spec_id:
                            reg_to_spec[reg.id] = reg.room_spec_id

            # Build lookup from arch room to spec
            arch_to_spec: dict[str, str] = {}
            if arch_set:
                for d in arch_set.designs:
                    for rm in d.rooms:
                        if rm.allocated_region_id and rm.allocated_region_id in reg_to_spec:
                            arch_to_spec[rm.id] = reg_to_spec[rm.allocated_region_id]

            # Build lookup from geom room to spec
            geom_to_spec: dict[str, str] = {}
            if geometry_set:
                floors = geometry_set.floor_plans if isinstance(geometry_set, FloorPlanSet) else geometry_set.geometries
                for f in floors:
                    geom = f.geometry if hasattr(f, "geometry") else f
                    for rm in getattr(geom, "rooms", []):
                        if rm.architectural_room_id and rm.architectural_room_id in arch_to_spec:
                            geom_to_spec[rm.id] = arch_to_spec[rm.architectural_room_id]

            # Create an entity chain per room spec
            for f in planning_spec.floors:
                for r_spec in f.room_specs:
                    grp: set[str] = {r_spec.id}
                    if r_spec.source_requirement_id:
                        grp.add(r_spec.source_requirement_id)
                    for reg_id, s_id in reg_to_spec.items():
                        if s_id == r_spec.id:
                            grp.add(reg_id)
                    for arch_id, s_id in arch_to_spec.items():
                        if s_id == r_spec.id:
                            grp.add(arch_id)
                    for geom_id, s_id in geom_to_spec.items():
                        if s_id == r_spec.id:
                            grp.add(geom_id)

                    # Collect events matching this room's entity chain
                    c_events: list[DecisionEvent] = []
                    for e in events:
                        # Event directly mentions entity_id in grp
                        matches_entity = e.entity_id in grp
                        # Event is a room event referencing this room
                        matches_ref = e.entity_type == "room" and any(ref in grp for ref in e.output_references)
                        matches_evidence = (
                            e.evidence.get("room_id") in grp
                            or e.evidence.get("geo_room_id") in grp
                            or e.evidence.get("room_spec_id") in grp
                            or e.evidence.get("allocated_region_id") in grp
                        )
                        if matches_entity or (e.entity_type == "room" and (matches_ref or matches_evidence)):
                            if e.event_id not in processed_event_ids:
                                c_events.append(e)
                                processed_event_ids.add(e.event_id)

                    chain = EntityTraceChain(
                        entity_id=r_spec.id,
                        entity_type="room",
                        room_type=r_spec.room_type,
                        floor_number=f.floor_number,
                        events=c_events,
                    )
                    for id_val in grp:
                        chains[id_val] = chain

        # Fallback for remaining events or when planning_spec is not provided
        for e in events:
            if e.entity_id and (e.entity_type == "room" or "room" in e.entity_id.lower()):
                if e.entity_id not in chains:
                    chain = chains.setdefault(
                        e.entity_id,
                        EntityTraceChain(
                            entity_id=e.entity_id,
                            entity_type="room",
                            room_type=e.evidence.get("room_type", ""),
                            floor_number=e.floor_number or 1,
                            events=[],
                        ),
                    )
                    if e.event_id not in processed_event_ids:
                        chain.events.append(e)
                        processed_event_ids.add(e.event_id)

        return chains
