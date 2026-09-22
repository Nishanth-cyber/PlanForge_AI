"""Authoritative computation of the 20 PlanForge research evaluation metrics.

Evaluates evidence-based architectural metrics across:
1. Requirement Adherence
2. Room Count Accuracy
3. Area Satisfaction
4. Allocation Adjacency
5. Separation Satisfaction
6. Attached Relationships
7. Boundary Compliance
8. Overlap Compliance
9. Connectivity
10. Door/Window Compliance
11. Staircase Compliance
12. Validation Success
13. Refinement Effectiveness
14. Multi-Design Diversity
15. Alternative Validity
16. Explainability Completeness
17. Trace Fabrication Safety
18. Computational Performance
19. ASAA Performance
20. Reproducibility
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from shapely.geometry import Polygon

from app.agents.diversity_agent.metrics import calculate_diversity_distance
from app.evaluation.models import MetricValue
from app.models.allocation import AllocationSet
from app.models.alternatives import DesignAlternativeSet
from app.models.floor_plan import FloorPlanSet
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.validation import ValidationReport
from app.orchestration.pipeline import PipelineResult


class MetricCalculator:
    """Computes all 20 research metrics from pipeline execution artifacts."""

    @classmethod
    def calculate_all(cls, result: PipelineResult, expected_props: Optional[Dict[str, Any]] = None) -> Dict[str, MetricValue]:
        """Compute all available metrics for a given pipeline result."""
        metrics: Dict[str, MetricValue] = {}

        reqs = result.requirements
        plan = result.planning_spec
        alloc = result.allocation_set
        floor_plans = result.floor_plan_set
        val_report = result.validation_report
        refine_res = result.refinement_result
        alts = result.alternative_set.alternatives if result.alternative_set else []
        trace = result.decision_trace
        stage_records = result.stage_records

        # 1. Requirement Adherence
        cls._calc_requirement_adherence(metrics, reqs, floor_plans, plan)

        # 2. Room Count Accuracy
        cls._calc_room_count_accuracy(metrics, reqs, floor_plans)

        # 3. Area Satisfaction
        cls._calc_area_satisfaction(metrics, plan, floor_plans)

        # 4. Allocation Adjacency
        cls._calc_allocation_adjacency(metrics, plan, alloc)

        # 5. Separation Satisfaction
        cls._calc_separation_satisfaction(metrics, plan, alloc)

        # 6. Attached Relationships
        cls._calc_attached_relationships(metrics, plan, alloc)

        # 7. Boundary Compliance
        cls._calc_boundary_compliance(metrics, val_report)

        # 8. Overlap Compliance
        cls._calc_overlap_compliance(metrics, val_report)

        # 9. Connectivity
        cls._calc_connectivity(metrics, val_report, floor_plans)

        # 10. Door/Window Compliance
        cls._calc_door_window_compliance(metrics, val_report, floor_plans)

        # 11. Staircase Compliance
        cls._calc_staircase_compliance(metrics, plan, alloc, floor_plans, val_report)

        # 12. Validation Success
        cls._calc_validation_success(metrics, val_report, result)

        # 13. Refinement Effectiveness
        cls._calc_refinement_effectiveness(metrics, refine_res, val_report)

        # 14. Multi-Design Diversity
        cls._calc_diversity(metrics, alts)

        # 15. Alternative Validity
        cls._calc_alternative_validity(metrics, alts)

        # 16. Explainability Completeness
        cls._calc_explainability_completeness(metrics, trace, plan)

        # 17. Trace Fabrication Safety
        cls._calc_trace_fabrication_safety(metrics, trace)

        # 18. Computational Performance
        cls._calc_performance(metrics, stage_records)

        # 19. ASAA Performance
        cls._calc_asaa_performance(metrics, alloc, stage_records)

        # 20. Reproducibility placeholder (evaluated via multi-run auditor)
        metrics["reproducibility_evaluated"] = MetricValue(
            name="reproducibility_evaluated",
            value=True,
            unit="flag",
            is_available=True,
        )

        return metrics

    # -------------------------------------------------------------------------
    # Metric 1: Requirement Adherence
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_requirement_adherence(
        cls,
        metrics: Dict[str, MetricValue],
        reqs: Optional[Requirements],
        floor_plans: Optional[FloorPlanSet],
        plan: Optional[PlanningSpec],
    ) -> None:
        if not reqs or not floor_plans:
            metrics["req_room_coverage"] = MetricValue.not_available(
                "req_room_coverage", "Requirements or FloorPlanSet artifact missing"
            )
            return

        req_rooms = sum(len(f.room_requirements) for f in reqs.floors) if reqs.floors else 0
        gen_rooms = sum(len(fp.geometry.rooms) for fp in floor_plans.floor_plans if fp.geometry)

        coverage = min(1.0, gen_rooms / max(1, req_rooms)) if req_rooms > 0 else 1.0
        metrics["req_room_coverage"] = MetricValue("req_room_coverage", round(coverage * 100.0, 1), "%")
        metrics["req_rooms_requested"] = MetricValue("req_rooms_requested", req_rooms, "count")
        metrics["req_rooms_generated"] = MetricValue("req_rooms_generated", gen_rooms, "count")

        # Floor assignment adherence
        req_floor_count = len(reqs.floors) if reqs.floors else reqs.target_floors or 1
        gen_floor_count = len(floor_plans.floor_plans)
        metrics["req_floor_count_adherence"] = MetricValue(
            "req_floor_count_adherence",
            100.0 if req_floor_count == gen_floor_count else round((gen_floor_count / max(1, req_floor_count)) * 100.0, 1),
            "%",
        )

    # -------------------------------------------------------------------------
    # Metric 2: Room Count Accuracy
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_room_count_accuracy(
        cls,
        metrics: Dict[str, MetricValue],
        reqs: Optional[Requirements],
        floor_plans: Optional[FloorPlanSet],
    ) -> None:
        if not reqs or not floor_plans:
            metrics["room_count_accuracy"] = MetricValue.not_available("room_count_accuracy", "Artifacts missing")
            return

        req_counts: Dict[str, int] = {}
        for f in reqs.floors:
            for r in f.room_requirements:
                cnt = getattr(r, "min_count", 1) or 1
                req_counts[r.room_type] = req_counts.get(r.room_type, 0) + cnt

        gen_counts: Dict[str, int] = {}
        for fp in floor_plans.floor_plans:
            if fp.geometry:
                for r in fp.geometry.rooms:
                    gen_counts[r.room_type] = gen_counts.get(r.room_type, 0) + 1

        # Auto-generated architectural circulation infrastructure (corridor, hallway, circulation)
        # does not count as an unrequested room surplus if not explicitly in requirements.
        CIRCULATION_TYPES = {"corridor", "hallway", "circulation", "passage"}
        all_types = set(req_counts.keys()).union(
            {t for t in gen_counts.keys() if t not in CIRCULATION_TYPES or t in req_counts}
        )
        if not all_types:
            metrics["room_count_accuracy"] = MetricValue("room_count_accuracy", 100.0, "%")
            return

        diffs = [abs(req_counts.get(t, 0) - gen_counts.get(t, 0)) for t in all_types]
        mae = sum(diffs) / len(diffs)
        metrics["room_count_mae"] = MetricValue("room_count_mae", round(mae, 2), "rooms")
        accuracy = max(0.0, 1.0 - (sum(diffs) / max(1, sum(req_counts.values())))) * 100.0
        metrics["room_count_accuracy"] = MetricValue("room_count_accuracy", round(accuracy, 1), "%")

    # -------------------------------------------------------------------------
    # Metric 3: Area Satisfaction
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_area_satisfaction(
        cls,
        metrics: Dict[str, MetricValue],
        plan: Optional[PlanningSpec],
        floor_plans: Optional[FloorPlanSet],
    ) -> None:
        if not plan or not floor_plans:
            metrics["area_min_compliance"] = MetricValue.not_available("area_min_compliance", "Artifacts missing")
            metrics["area_preferred_mae"] = MetricValue.not_available("area_preferred_mae", "Artifacts missing")
            return

        room_spec_map = {}
        for f in plan.floors:
            for r in f.room_specs:
                room_spec_map[r.id] = r

        min_compliant = 0
        preferred_diffs: List[float] = []
        max_violations = 0
        total_matched = 0

        for fp in floor_plans.floor_plans:
            if not fp.geometry:
                continue
            for r in fp.geometry.rooms:
                target_spec = None
                # Match by source requirement id or spec id
                for spec in room_spec_map.values():
                    if spec.id == r.id or spec.room_type == r.room_type:
                        target_spec = spec
                        break

                if target_spec:
                    total_matched += 1
                    actual_area = r.area_sqm
                    min_bound = target_spec.min_area_sqm if target_spec.min_area_sqm is not None else 5.0
                    if actual_area >= (min_bound - 0.1):
                        min_compliant += 1
                    if target_spec.target_area_sqm is not None:
                        preferred_diffs.append(abs(actual_area - target_spec.target_area_sqm))
                    if target_spec.max_area_sqm is not None and actual_area > (target_spec.max_area_sqm + 0.1):
                        max_violations += 1

        comp_pct = (min_compliant / max(1, total_matched)) * 100.0 if total_matched > 0 else 100.0
        mae = (sum(preferred_diffs) / max(1, len(preferred_diffs))) if preferred_diffs else 0.0

        metrics["area_min_compliance"] = MetricValue("area_min_compliance", round(comp_pct, 1), "%")
        metrics["area_preferred_mae"] = MetricValue("area_preferred_mae", round(mae, 2), "m²")
        metrics["area_max_violations"] = MetricValue("area_max_violations", max_violations, "count")

    # -------------------------------------------------------------------------
    # Metric 4: Allocation Adjacency
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_allocation_adjacency(
        cls,
        metrics: Dict[str, MetricValue],
        plan: Optional[PlanningSpec],
        alloc: Optional[AllocationSet],
    ) -> None:
        if not plan or not alloc:
            metrics["allocation_adjacency_compliance"] = MetricValue.not_available(
                "allocation_adjacency_compliance", "PlanningSpec or AllocationSet missing"
            )
            return

        adj_pairs: set[tuple[str, str]] = set()
        for f in plan.floors:
            for r_id, adjs in f.adjacency_matrix.items():
                for a_id in adjs:
                    if r_id != a_id:
                        adj_pairs.add((min(r_id, a_id), max(r_id, a_id)))
            for r in f.room_specs:
                for a_id in r.adjacency:
                    if r.id != a_id:
                        adj_pairs.add((min(r.id, a_id), max(r.id, a_id)))

        if not adj_pairs:
            metrics["allocation_adjacency_compliance"] = MetricValue(
                "allocation_adjacency_compliance", 100.0, "%", is_available=True
            )
            return

        satisfied = 0
        total = len(adj_pairs)

        reg_by_spec: Dict[str, Any] = {}
        reg_by_type: Dict[str, Any] = {}
        reg_by_norm: Dict[str, Any] = {}

        def _norm(name: str) -> str:
            n = name.lower().replace(" ", "_").replace("-", "_")
            return n[:-5] if n.endswith("_room") else n

        for a in alloc.allocations:
            for r in a.allocated_regions:
                if r.room_spec_id:
                    reg_by_spec[r.room_spec_id] = r
                if r.room_type:
                    reg_by_type[r.room_type] = r
                    reg_by_norm[_norm(r.room_type)] = r

        def _find_reg(key: str) -> Optional[Any]:
            return reg_by_spec.get(key) or reg_by_type.get(key) or reg_by_norm.get(_norm(key))

        for r1, r2 in adj_pairs:
            reg1 = _find_reg(r1)
            reg2 = _find_reg(r2)
            if reg1 and reg2:
                from app.asaa.spatial_regions import are_regions_adjacent
                is_adj = (
                    reg2.id in reg1.adjacency_regions
                    or reg1.id in reg2.adjacency_regions
                    or are_regions_adjacent(reg1.polygon, reg2.polygon, min_contact_m=0.05)
                )
                if is_adj:
                    satisfied += 1

        compliance = (satisfied / max(1, total)) * 100.0
        metrics["allocation_adjacency_compliance"] = MetricValue(
            "allocation_adjacency_compliance", round(compliance, 1), "%"
        )
        metrics["allocation_adjacency_satisfied"] = MetricValue("allocation_adjacency_satisfied", satisfied, "count")
        metrics["allocation_adjacency_total"] = MetricValue("allocation_adjacency_total", total, "count")

    # -------------------------------------------------------------------------
    # Metric 5: Separation Satisfaction
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_separation_satisfaction(
        cls,
        metrics: Dict[str, MetricValue],
        plan: Optional[PlanningSpec],
        alloc: Optional[AllocationSet],
    ) -> None:
        if not plan or not alloc:
            metrics["separation_compliance"] = MetricValue.not_available("separation_compliance", "Artifacts missing")
            return

        sep_pairs: set[tuple[str, str]] = set()
        for f in plan.floors:
            for r_id, avoids in f.avoid_matrix.items():
                for av_id in avoids:
                    if r_id != av_id:
                        sep_pairs.add((min(r_id, av_id), max(r_id, av_id)))
            for r in f.room_specs:
                for av_id in r.avoid:
                    if r.id != av_id:
                        sep_pairs.add((min(r.id, av_id), max(r.id, av_id)))

        if not sep_pairs:
            metrics["separation_compliance"] = MetricValue("separation_compliance", 100.0, "%", is_available=True)
            return

        satisfied = 0
        total = len(sep_pairs)

        def _norm(name: str) -> str:
            n = name.lower().replace(" ", "_").replace("-", "_")
            return n[:-5] if n.endswith("_room") else n

        reg_by_spec: Dict[str, Any] = {}
        reg_by_type: Dict[str, Any] = {}
        reg_by_norm: Dict[str, Any] = {}

        for a in alloc.allocations:
            for r in a.allocated_regions:
                if r.room_spec_id:
                    reg_by_spec[r.room_spec_id] = r
                if r.room_type:
                    reg_by_type[r.room_type] = r
                    reg_by_norm[_norm(r.room_type)] = r

        def _find_reg(key: str) -> Optional[Any]:
            return reg_by_spec.get(key) or reg_by_type.get(key) or reg_by_norm.get(_norm(key))

        for r1, r2 in sep_pairs:
            reg1 = _find_reg(r1)
            reg2 = _find_reg(r2)
            if reg1 and reg2:
                from app.asaa.spatial_regions import are_regions_adjacent
                is_adj = (
                    reg2.id in reg1.adjacency_regions
                    or reg1.id in reg2.adjacency_regions
                    or are_regions_adjacent(reg1.polygon, reg2.polygon, min_contact_m=0.05)
                )
                if not is_adj:
                    satisfied += 1
            else:
                satisfied += 1

        compliance = (satisfied / max(1, total)) * 100.0
        metrics["separation_compliance"] = MetricValue("separation_compliance", round(compliance, 1), "%")

    # -------------------------------------------------------------------------
    # Metric 6: Attached Relationships
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_attached_relationships(
        cls,
        metrics: Dict[str, MetricValue],
        plan: Optional[PlanningSpec],
        alloc: Optional[AllocationSet],
    ) -> None:
        if not plan or not alloc:
            metrics["attached_suite_compliance"] = MetricValue.not_available("attached_suite_compliance", "Artifacts missing")
            return

        attached_pairs = []
        for r in plan.all_room_specs():
            if r.attached_to_room_id:
                attached_pairs.append((r.id, r.attached_to_room_id))

        if not attached_pairs:
            metrics["attached_suite_compliance"] = MetricValue("attached_suite_compliance", 100.0, "%", is_available=True)
            return

        satisfied = 0
        total = len(attached_pairs)
        reg_by_spec = {}
        reg_by_type = {}
        for a in alloc.allocations:
            for r in a.allocated_regions:
                if r.room_spec_id:
                    reg_by_spec[r.room_spec_id] = r
                if r.room_type:
                    reg_by_type[r.room_type] = r

        for r1, parent_id in attached_pairs:
            reg1 = reg_by_spec.get(r1) or reg_by_type.get(r1)
            reg2 = reg_by_spec.get(parent_id) or reg_by_type.get(parent_id)
            if reg1 and reg2 and (reg2.id in reg1.adjacency_regions or reg1.id in reg2.adjacency_regions):
                satisfied += 1

        comp = (satisfied / max(1, total)) * 100.0
        metrics["attached_suite_compliance"] = MetricValue("attached_suite_compliance", round(comp, 1), "%")

    # -------------------------------------------------------------------------
    # Metric 7: Boundary Compliance
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_boundary_compliance(
        cls,
        metrics: Dict[str, MetricValue],
        val_report: Optional[ValidationReport],
    ) -> None:
        if not val_report:
            metrics["boundary_compliance"] = MetricValue.not_available("boundary_compliance", "ValidationReport missing")
            return

        boundary_errors = 0
        for res in val_report.results:
            for issue in res.issues:
                if issue.category == "boundary" and issue.severity == "error":
                    boundary_errors += 1

        metrics["boundary_compliance"] = MetricValue(
            "boundary_compliance",
            100.0 if boundary_errors == 0 else 0.0,
            "%",
        )
        metrics["boundary_violation_count"] = MetricValue("boundary_violation_count", boundary_errors, "count")

    # -------------------------------------------------------------------------
    # Metric 8: Overlap Compliance
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_overlap_compliance(
        cls,
        metrics: Dict[str, MetricValue],
        val_report: Optional[ValidationReport],
    ) -> None:
        if not val_report:
            metrics["overlap_free"] = MetricValue.not_available("overlap_free", "ValidationReport missing")
            return

        overlap_errors = 0
        for res in val_report.results:
            for issue in res.issues:
                if issue.category == "overlap" and issue.severity == "error":
                    overlap_errors += 1

        metrics["overlap_free"] = MetricValue("overlap_free", overlap_errors == 0, "bool")
        metrics["overlap_violation_count"] = MetricValue("overlap_violation_count", overlap_errors, "count")

    # -------------------------------------------------------------------------
    # Metric 9: Connectivity
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_connectivity(
        cls,
        metrics: Dict[str, MetricValue],
        val_report: Optional[ValidationReport],
        floor_plans: Optional[FloorPlanSet],
    ) -> None:
        if not val_report or not floor_plans:
            metrics["connectivity_rate"] = MetricValue.not_available("connectivity_rate", "Artifacts missing")
            return

        conn_errors = 0
        for res in val_report.results:
            for issue in res.issues:
                if issue.category == "connectivity" and issue.severity == "error":
                    conn_errors += 1

        total_rooms = sum(len(fp.geometry.rooms) for fp in floor_plans.floor_plans if fp.geometry)
        unconnected = min(total_rooms, conn_errors)
        connected_rooms = max(0, total_rooms - unconnected)
        conn_rate = (connected_rooms / max(1, total_rooms)) * 100.0

        metrics["connectivity_rate"] = MetricValue("connectivity_rate", round(conn_rate, 1), "%")
        metrics["disconnected_room_count"] = MetricValue("disconnected_room_count", conn_errors, "count")

    # -------------------------------------------------------------------------
    # Metric 10: Door/Window Compliance
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_door_window_compliance(
        cls,
        metrics: Dict[str, MetricValue],
        val_report: Optional[ValidationReport],
        floor_plans: Optional[FloorPlanSet],
    ) -> None:
        if not floor_plans:
            metrics["door_compliance"] = MetricValue.not_available("door_compliance", "FloorPlanSet missing")
            return

        total_doors = sum(len(fp.geometry.doors) for fp in floor_plans.floor_plans if fp.geometry)
        total_windows = sum(len(fp.geometry.windows) for fp in floor_plans.floor_plans if fp.geometry)

        door_errors = 0
        window_errors = 0
        if val_report:
            for res in val_report.results:
                for issue in res.issues:
                    if issue.category == "door" and issue.severity == "error":
                        door_errors += 1
                    elif issue.category == "window" and issue.severity == "error":
                        window_errors += 1

        metrics["door_compliance"] = MetricValue(
            "door_compliance",
            100.0 if door_errors == 0 else max(0.0, (1.0 - door_errors / max(1, total_doors)) * 100.0),
            "%",
        )
        metrics["total_doors"] = MetricValue("total_doors", total_doors, "count")
        metrics["total_windows"] = MetricValue("total_windows", total_windows, "count")

    # -------------------------------------------------------------------------
    # Metric 11: Staircase Compliance
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_staircase_compliance(
        cls,
        metrics: Dict[str, MetricValue],
        plan: Optional[PlanningSpec],
        alloc: Optional[AllocationSet],
        floor_plans: Optional[FloorPlanSet],
        val_report: Optional[ValidationReport],
    ) -> None:
        if not floor_plans or len(floor_plans.floor_plans) < 2:
            metrics["staircase_compliance"] = MetricValue.not_available(
                "staircase_compliance", "Single-floor plan; staircase not required"
            )
            return

        stair_errors = 0
        if val_report:
            for res in val_report.results:
                for issue in res.issues:
                    if issue.category == "staircase" and issue.severity == "error":
                        stair_errors += 1

        stair_count = sum(len(fp.geometry.staircases) for fp in floor_plans.floor_plans if fp.geometry)
        aligned = getattr(alloc, "staircase_aligned", False) if alloc else False

        metrics["staircase_compliance"] = MetricValue(
            "staircase_compliance",
            100.0 if (stair_errors == 0 and stair_count >= 1) else 0.0,
            "%",
        )
        metrics["staircase_aligned"] = MetricValue("staircase_aligned", aligned, "bool")

    # -------------------------------------------------------------------------
    # Metric 12: Validation Success
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_validation_success(
        cls,
        metrics: Dict[str, MetricValue],
        val_report: Optional[ValidationReport],
        result: PipelineResult,
    ) -> None:
        if not val_report:
            metrics["validation_success"] = MetricValue("validation_success", result.is_success, "bool")
            metrics["validation_error_count"] = MetricValue("validation_error_count", 0, "count")
            metrics["validation_warning_count"] = MetricValue("validation_warning_count", 0, "count")
            metrics["validation_score"] = MetricValue("validation_score", 100.0 if result.is_success else 0.0, "points")
            return

        metrics["validation_success"] = MetricValue("validation_success", val_report.overall_valid, "bool")
        metrics["validation_error_count"] = MetricValue("validation_error_count", val_report.total_errors, "count")
        metrics["validation_warning_count"] = MetricValue("validation_warning_count", val_report.total_warnings, "count")
        metrics["validation_score"] = MetricValue("validation_score", val_report.overall_score, "points")

    # -------------------------------------------------------------------------
    # Metric 13: Refinement Effectiveness
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_refinement_effectiveness(
        cls,
        metrics: Dict[str, MetricValue],
        refine_res: Any,
        val_report: Optional[ValidationReport],
    ) -> None:
        if not refine_res:
            metrics["refinement_error_reduction"] = MetricValue.not_available(
                "refinement_error_reduction", "Refinement not triggered or loop disabled"
            )
            return

        init_errs = 0
        final_errs = 0
        iterations_list = getattr(refine_res, "iterations", None) or getattr(refine_res, "iteration_records", None)
        if iterations_list:
            init_errs = getattr(iterations_list[0], "error_count", 0)
            final_errs = getattr(iterations_list[-1], "error_count", 0)
        elif val_report:
            final_errs = val_report.total_errors

        init_errs = getattr(refine_res, "initial_error_count", init_errs)
        final_errs = getattr(refine_res, "final_error_count", final_errs)
        reduction = max(0, init_errs - final_errs)
        iterations = getattr(refine_res, "total_iterations", len(iterations_list) if iterations_list else 0)
        converged = getattr(refine_res, "is_valid", final_errs == 0)

        metrics["refinement_initial_errors"] = MetricValue("refinement_initial_errors", init_errs, "count")
        metrics["refinement_final_errors"] = MetricValue("refinement_final_errors", final_errs, "count")
        metrics["refinement_error_reduction"] = MetricValue("refinement_error_reduction", reduction, "count")
        metrics["refinement_iterations"] = MetricValue("refinement_iterations", iterations, "iterations")
        metrics["refinement_converged"] = MetricValue("refinement_converged", converged, "bool")

    # -------------------------------------------------------------------------
    # Metric 14: Multi-Design Diversity
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_diversity(
        cls,
        metrics: Dict[str, MetricValue],
        alts: List[Any],
    ) -> None:
        if len(alts) < 2:
            metrics["diversity_mean_distance"] = MetricValue.not_available(
                "diversity_mean_distance", "Single alternative run; diversity requires >= 2 alternatives"
            )
            metrics["diversity_duplicate_count"] = MetricValue("diversity_duplicate_count", 0, "count")
            return

        distances: List[float] = []
        dup_count = 0
        near_dup_count = 0

        for i in range(len(alts)):
            sig_i = getattr(alts[i], "signature", None)
            if not sig_i:
                continue
            for j in range(i + 1, len(alts)):
                sig_j = getattr(alts[j], "signature", None)
                if not sig_j:
                    continue
                dist = calculate_diversity_distance(sig_i, sig_j)
                distances.append(dist)
                if dist < 0.05:
                    dup_count += 1
                elif dist < 0.20:
                    near_dup_count += 1

        mean_dist = sum(distances) / max(1, len(distances)) if distances else 0.0
        metrics["diversity_mean_distance"] = MetricValue("diversity_mean_distance", round(mean_dist, 3), "[0-1]")
        metrics["diversity_duplicate_count"] = MetricValue("diversity_duplicate_count", dup_count, "count")
        metrics["diversity_near_duplicate_count"] = MetricValue("diversity_near_duplicate_count", near_dup_count, "count")

    # -------------------------------------------------------------------------
    # Metric 15: Alternative Validity
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_alternative_validity(
        cls,
        metrics: Dict[str, MetricValue],
        alts: List[Any],
    ) -> None:
        if not alts:
            metrics["alternative_validity_rate"] = MetricValue.not_available(
                "alternative_validity_rate", "No alternatives generated"
            )
            return

        valid_count = sum(1 for a in alts if getattr(a, "overall_valid", False))
        rate = (valid_count / max(1, len(alts))) * 100.0
        metrics["alternative_validity_rate"] = MetricValue("alternative_validity_rate", round(rate, 1), "%")
        metrics["alternatives_generated_count"] = MetricValue("alternatives_generated_count", len(alts), "count")
        metrics["alternatives_valid_count"] = MetricValue("alternatives_valid_count", valid_count, "count")

    # -------------------------------------------------------------------------
    # Metric 16: Explainability Completeness
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_explainability_completeness(
        cls,
        metrics: Dict[str, MetricValue],
        trace: Any,
        plan: Optional[PlanningSpec],
    ) -> None:
        if not trace:
            metrics["trace_completeness"] = MetricValue.not_available("trace_completeness", "DecisionTrace missing")
            return

        stages = getattr(trace, "stages", [])
        stage_coverage = (len(stages) / 10.0) * 100.0

        entity_chains = getattr(trace, "entity_chains", {})
        total_rooms = sum(len(f.room_specs) for f in plan.floors) if plan else len(entity_chains)
        chain_completeness = (len(entity_chains) / max(1, total_rooms)) * 100.0 if total_rooms > 0 else 100.0

        metrics["trace_stage_coverage"] = MetricValue("trace_stage_coverage", round(stage_coverage, 1), "%")
        metrics["trace_entity_chain_completeness"] = MetricValue(
            "trace_entity_chain_completeness", round(chain_completeness, 1), "%"
        )
        metrics["trace_total_events"] = MetricValue(
            "trace_total_events", sum(len(getattr(s, "events", [])) for s in stages), "count"
        )

    # -------------------------------------------------------------------------
    # Metric 17: Trace Fabrication Safety
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_trace_fabrication_safety(
        cls,
        metrics: Dict[str, MetricValue],
        trace: Any,
    ) -> None:
        if not trace:
            metrics["trace_no_fabrication_audit"] = MetricValue.not_available(
                "trace_no_fabrication_audit", "DecisionTrace missing"
            )
            return

        # Audit events: ensure genuine source provenance and zero synthetic reasoning leakage
        stages = getattr(trace, "stages", [])
        fabrication_detected = False

        for s in stages:
            for ev in getattr(s, "events", []):
                src = getattr(ev, "source", None)
                if not src:
                    fabrication_detected = True
                    break
                reason_str = str(getattr(ev, "reason", "")).lower()
                if "chain_of_thought" in reason_str or "scratchpad" in reason_str:
                    fabrication_detected = True
                    break
            if fabrication_detected:
                break

        metrics["trace_no_fabrication_audit"] = MetricValue(
            "trace_no_fabrication_audit", not fabrication_detected, "bool"
        )

    # -------------------------------------------------------------------------
    # Metric 18: Computational Performance
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_performance(
        cls,
        metrics: Dict[str, MetricValue],
        stage_records: Dict[str, Any],
    ) -> None:
        total_time = 0.0
        for name, rec in stage_records.items():
            dur = getattr(rec, "duration_ms", 0.0) or 0.0
            total_time += dur
            metrics[f"timing_{name.lower()}_ms"] = MetricValue(f"timing_{name.lower()}_ms", round(dur, 2), "ms")

        metrics["timing_total_ms"] = MetricValue("timing_total_ms", round(total_time, 2), "ms")

    # -------------------------------------------------------------------------
    # Metric 19: ASAA Performance
    # -------------------------------------------------------------------------
    @classmethod
    def _calc_asaa_performance(
        cls,
        metrics: Dict[str, MetricValue],
        alloc: Optional[AllocationSet],
        stage_records: Dict[str, Any],
    ) -> None:
        asaa_rec = stage_records.get("ASAA")
        asaa_ms = getattr(asaa_rec, "duration_ms", 0.0) if asaa_rec else 0.0

        metrics["asaa_duration_ms"] = MetricValue("asaa_duration_ms", round(asaa_ms, 2), "ms")

        if alloc and asaa_ms > 0:
            num_regions = sum(len(a.allocated_regions) for a in alloc.allocations)
            rate = num_regions / (asaa_ms / 1000.0)
            metrics["asaa_allocation_rate"] = MetricValue("asaa_allocation_rate", round(rate, 1), "regions/sec")
        else:
            metrics["asaa_allocation_rate"] = MetricValue.not_available(
                "asaa_allocation_rate", "ASAA duration zero or allocation set missing"
            )
