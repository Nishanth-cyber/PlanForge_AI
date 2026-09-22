"""Controlled ablation study framework for PlanForge research evaluation.

Strict Experimental Control Invariants:
1. Input brief, plot boundary, setbacks, and room requirements remain 100% constant across variants.
2. Mock LLM configuration, random seed, and validation rules remain 100% identical.
3. Only the specific isolated factor (ASAA allocator, Refinement loop, or Diversity count) is altered.
4. Outputs are captured side-by-side without contamination of production components.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.evaluation.baselines import BaselineSpatialAllocator
from app.evaluation.models import AblationResult, BenchmarkCase
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.pipeline import PipelineResult


class AblationStudyCoordinator:
    """Orchestrates controlled ablation experiments across PlanForge variants."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def evaluate_asaa_ablation(
        self,
        case: BenchmarkCase,
        full_orchestrator: PlanForgeOrchestrator,
        baseline_allocator: Optional[BaselineSpatialAllocator] = None,
        output_dir: str = "results/ablation/asaa",
    ) -> AblationResult:
        """Ablation B: Full PlanForge (with ASAA) vs Without ASAA (Baseline Proportional Slice).

        Keeps downstream Architectural LLM, Geometry Engine, and Validator identical.
        """
        b_alloc = baseline_allocator or BaselineSpatialAllocator()

        # Build baseline orchestrator with identical downstream components but baseline allocator
        baseline_orchestrator = PlanForgeOrchestrator(
            requirement_agent=full_orchestrator.requirement_agent,
            planning_agent=full_orchestrator.planning_agent,
            asaa_allocator=b_alloc,  # Replaced component
            architectural_agent=full_orchestrator.architectural_agent,
            geometry_engine=full_orchestrator.geometry_engine,
            validator=full_orchestrator.validator,
            refinement_loop=full_orchestrator.refinement_loop,
        )

        cfg = OrchestrationConfig(
            output_dir=output_dir,
            enable_refinement=False,  # Isolate pure allocation impact without refinement compensation
            enable_rendering=False,
            enable_exports=False,
        )

        pname = f"{case.name}_Ablation_ASAA"
        res_full = full_orchestrator.generate(case.brief, project_name=pname, config=cfg)
        res_baseline = baseline_orchestrator.generate(case.brief, project_name=pname, config=cfg)

        metrics_full = self._extract_key_metrics(res_full)
        metrics_base = self._extract_key_metrics(res_baseline)

        deltas = {}
        for k in metrics_full:
            if isinstance(metrics_full[k], (int, float)) and isinstance(metrics_base.get(k), (int, float)):
                deltas[f"{k}_delta"] = round(float(metrics_full[k]) - float(metrics_base[k]), 4)

        return AblationResult(
            ablation_id=f"ablation_asaa_{case.case_id}",
            case_id=case.case_id,
            variant_a_name="Full_PlanForge_ASAA",
            variant_a_metrics=metrics_full,
            variant_b_name="Without_ASAA_Baseline",
            variant_b_metrics=metrics_base,
            deltas=deltas,
        )

    def evaluate_refinement_ablation(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        output_dir: str = "results/ablation/refinement",
    ) -> AblationResult:
        """Ablation C: With Refinement vs Without Refinement.

        Keeps requirements, planning, allocation, and initial architectural design identical.
        """
        cfg_with = OrchestrationConfig(
            output_dir=output_dir,
            enable_refinement=True,
            max_refinement_iterations=3,
            enable_rendering=False,
            enable_exports=False,
        )

        cfg_without = OrchestrationConfig(
            output_dir=output_dir,
            enable_refinement=False,
            enable_rendering=False,
            enable_exports=False,
        )

        res_with = orchestrator.generate(case.brief, project_name=f"{case.name}_With_Refinement", config=cfg_with)
        res_without = orchestrator.generate(case.brief, project_name=f"{case.name}_Without_Refinement", config=cfg_without)

        metrics_with = self._extract_key_metrics(res_with)
        metrics_without = self._extract_key_metrics(res_without)

        # Refinement specific metrics
        err_with = metrics_with.get("validation_error_count", 0)
        err_without = metrics_without.get("validation_error_count", 0)
        err_reduction = err_without - err_with

        deltas = {
            "error_reduction": float(err_reduction),
            "validity_gain": 1.0 if (metrics_with.get("overall_valid") and not metrics_without.get("overall_valid")) else 0.0,
        }

        return AblationResult(
            ablation_id=f"ablation_refinement_{case.case_id}",
            case_id=case.case_id,
            variant_a_name="With_Refinement",
            variant_a_metrics=metrics_with,
            variant_b_name="Without_Refinement",
            variant_b_metrics=metrics_without,
            deltas=deltas,
        )

    def evaluate_diversity_ablation(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        counts: Optional[List[int]] = None,
        output_dir: str = "results/ablation/diversity",
    ) -> AblationResult:
        """Ablation D: Single design (1 alternative) vs Multiple designs (e.g. 3 alternatives)."""
        c_list = counts or [1, 3]

        cfg_single = OrchestrationConfig(
            output_dir=output_dir,
            num_alternatives=c_list[0],
            enable_refinement=True,
            enable_rendering=False,
            enable_exports=False,
        )

        cfg_multi = OrchestrationConfig(
            output_dir=output_dir,
            num_alternatives=c_list[1],
            enable_refinement=True,
            enable_rendering=False,
            enable_exports=False,
        )

        res_single = orchestrator.generate(case.brief, project_name=f"{case.name}_Div_Single", config=cfg_single)
        res_multi = orchestrator.generate(case.brief, project_name=f"{case.name}_Div_Multi", config=cfg_multi)

        metrics_single = self._extract_key_metrics(res_single)
        metrics_multi = self._extract_key_metrics(res_multi)

        # Multi-alternative details
        alts_multi = res_multi.alternative_set.alternatives if res_multi.alternative_set else []
        alts_single = res_single.alternative_set.alternatives if res_single.alternative_set else []
        metrics_multi["num_alternatives_generated"] = len(alts_multi)
        metrics_multi["valid_alternatives_count"] = sum(1 for a in alts_multi if a.is_valid)

        deltas = {
            "alternatives_count_delta": float(len(alts_multi) - len(alts_single)),
        }

        return AblationResult(
            ablation_id=f"ablation_diversity_{case.case_id}",
            case_id=case.case_id,
            variant_a_name=f"Multi_Alternatives_{c_list[1]}",
            variant_a_metrics=metrics_multi,
            variant_b_name=f"Single_Alternative_{c_list[0]}",
            variant_b_metrics=metrics_single,
            deltas=deltas,
        )

    def _extract_key_metrics(self, res: PipelineResult) -> Dict[str, Any]:
        """Extract comparable numeric & boolean metrics from a pipeline execution result."""
        vr = res.validation_report
        out: Dict[str, Any] = {
            "is_success": res.is_success,
            "overall_valid": vr.overall_valid if vr else False,
            "quality_score": vr.overall_score if vr else 0.0,
            "validation_error_count": vr.total_errors if vr else 0,
            "validation_warning_count": vr.total_warnings if vr else 0,
            "total_execution_ms": sum(s.duration_ms for s in res.stage_records.values() if s.duration_ms),
        }

        if res.allocation_set:
            total_allocated = sum(a.total_area_sqm for a in res.allocation_set.allocations)
            out["total_allocated_area_sqm"] = round(total_allocated, 2)
            out["num_allocated_regions"] = sum(len(a.allocated_regions) for a in res.allocation_set.allocations)
            out["allocation_score"] = round(
                sum(a.score for a in res.allocation_set.allocations) / max(1, len(res.allocation_set.allocations)), 2
            )

        if res.floor_plan_set:
            out["num_constructed_rooms"] = sum(
                len(fp.geometry.rooms) for fp in res.floor_plan_set.floor_plans if fp.geometry
            )

        from app.evaluation.metrics import MetricCalculator
        calculated = MetricCalculator.calculate_all(res)
        for m_name in [
            "allocation_adjacency_compliance",
            "area_preferred_mae",
            "area_min_compliance",
            "boundary_compliance",
            "connectivity_rate",
            "separation_compliance",
        ]:
            if m_name in calculated and calculated[m_name].is_available:
                out[m_name] = calculated[m_name].value

        return out
