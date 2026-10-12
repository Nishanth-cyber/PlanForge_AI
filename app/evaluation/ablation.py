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

    def evaluate_candidate_budget_ablation(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        budgets: Optional[List[int]] = None,
        output_dir: str = "results/ablation/candidate_budget",
    ) -> AblationResult:
        """Ablation A: ASAA Candidate Exploration Budget (e.g. 1 candidate vs 3 candidates)."""
        b_list = budgets or [1, 3]

        cfg_low = OrchestrationConfig(
            output_dir=output_dir,
            candidate_budget=b_list[0],
            enable_refinement=False,
            enable_rendering=False,
            enable_exports=False,
        )
        cfg_high = OrchestrationConfig(
            output_dir=output_dir,
            candidate_budget=b_list[1],
            enable_refinement=False,
            enable_rendering=False,
            enable_exports=False,
        )

        res_low = orchestrator.generate(case.brief, project_name=f"{case.name}_Budget_{b_list[0]}", config=cfg_low)
        res_high = orchestrator.generate(case.brief, project_name=f"{case.name}_Budget_{b_list[1]}", config=cfg_high)

        metrics_low = self._extract_key_metrics(res_low)
        metrics_high = self._extract_key_metrics(res_high)

        deltas = {
            "score_delta": round(float(metrics_high.get("quality_score", 0.0)) - float(metrics_low.get("quality_score", 0.0)), 2),
            "runtime_delta_ms": round(float(metrics_high.get("total_execution_ms", 0.0)) - float(metrics_low.get("total_execution_ms", 0.0)), 1),
        }

        return AblationResult(
            ablation_id=f"ablation_cand_budget_{case.case_id}",
            case_id=case.case_id,
            variant_a_name=f"Budget_{b_list[1]}_Candidates",
            variant_a_metrics=metrics_high,
            variant_b_name=f"Budget_{b_list[0]}_Candidate",
            variant_b_metrics=metrics_low,
            deltas=deltas,
        )

    def evaluate_llm_action_selection_ablation(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        output_dir: str = "results/ablation/llm_selection",
    ) -> AblationResult:
        """Ablation B: LLM Action Selection with Deterministic Fallback vs Deterministic Rule-Based Selection."""
        cfg_llm = OrchestrationConfig(
            mode="agentic",
            use_llm=True,
            output_dir=output_dir,
            enable_rendering=False,
            enable_exports=False,
        )
        cfg_rule = OrchestrationConfig(
            mode="agentic",
            use_llm=False,
            output_dir=output_dir,
            enable_rendering=False,
            enable_exports=False,
        )

        res_llm = orchestrator.generate(case.brief, project_name=f"{case.name}_LLM_Select", config=cfg_llm)
        res_rule = orchestrator.generate(case.brief, project_name=f"{case.name}_Rule_Select", config=cfg_rule)

        metrics_llm = self._extract_key_metrics(res_llm)
        metrics_rule = self._extract_key_metrics(res_rule)

        deltas = {
            "score_delta": round(float(metrics_llm.get("quality_score", 0.0)) - float(metrics_rule.get("quality_score", 0.0)), 2),
            "runtime_delta_ms": round(float(metrics_llm.get("total_execution_ms", 0.0)) - float(metrics_rule.get("total_execution_ms", 0.0)), 1),
        }

        return AblationResult(
            ablation_id=f"ablation_llm_action_{case.case_id}",
            case_id=case.case_id,
            variant_a_name="LLM_Action_Selector",
            variant_a_metrics=metrics_llm,
            variant_b_name="Deterministic_Rule_Selector",
            variant_b_metrics=metrics_rule,
            deltas=deltas,
        )

    def evaluate_multi_agent_coordination_ablation(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        output_dir: str = "results/ablation/multi_agent",
    ) -> AblationResult:
        """Ablation C: Hierarchical Multi-Agent Coordination vs Single-Agent Pipeline Baseline."""
        cfg_multi = OrchestrationConfig(
            mode="multi_agent",
            output_dir=output_dir,
            enable_rendering=False,
            enable_exports=False,
        )
        cfg_pipe = OrchestrationConfig(
            mode="pipeline",
            output_dir=output_dir,
            enable_rendering=False,
            enable_exports=False,
        )

        res_multi = orchestrator.generate(case.brief, project_name=f"{case.name}_MultiAgent", config=cfg_multi)
        res_pipe = orchestrator.generate(case.brief, project_name=f"{case.name}_Pipeline", config=cfg_pipe)

        metrics_multi = self._extract_key_metrics(res_multi)
        metrics_pipe = self._extract_key_metrics(res_pipe)

        deltas = {
            "score_delta": round(float(metrics_multi.get("quality_score", 0.0)) - float(metrics_pipe.get("quality_score", 0.0)), 2),
            "runtime_delta_ms": round(float(metrics_multi.get("total_execution_ms", 0.0)) - float(metrics_pipe.get("total_execution_ms", 0.0)), 1),
        }

        return AblationResult(
            ablation_id=f"ablation_coordination_{case.case_id}",
            case_id=case.case_id,
            variant_a_name="Hierarchical_Multi_Agent",
            variant_a_metrics=metrics_multi,
            variant_b_name="Pipeline_Baseline",
            variant_b_metrics=metrics_pipe,
            deltas=deltas,
        )

    def evaluate_clarification_ablation(
        self,
        case: BenchmarkCase,
        orchestrator: PlanForgeOrchestrator,
        output_dir: str = "results/ablation/clarification",
    ) -> AblationResult:
        """Ablation E: Interactive Clarification Mode vs Non-Interactive Batch Mode."""
        cfg_interactive = OrchestrationConfig(
            mode="multi_agent",
            interactive=True,
            output_dir=output_dir,
            enable_rendering=False,
            enable_exports=False,
        )
        cfg_batch = OrchestrationConfig(
            mode="multi_agent",
            interactive=False,
            output_dir=output_dir,
            enable_rendering=False,
            enable_exports=False,
        )

        res_interactive = orchestrator.generate(case.brief, project_name=f"{case.name}_Interactive", config=cfg_interactive)
        res_batch = orchestrator.generate(case.brief, project_name=f"{case.name}_Batch", config=cfg_batch)

        metrics_interactive = self._extract_key_metrics(res_interactive)
        metrics_batch = self._extract_key_metrics(res_batch)

        metrics_interactive["status"] = res_interactive.status
        metrics_batch["status"] = res_batch.status

        deltas = {
            "clarification_triggered": 1.0 if res_interactive.status == "waiting_for_clarification" else 0.0,
            "truthful_halt": 1.0 if res_batch.status in ("failed", "incomplete_requirements") else 0.0,
        }

        return AblationResult(
            ablation_id=f"ablation_clarification_{case.case_id}",
            case_id=case.case_id,
            variant_a_name="Interactive_Clarification_Mode",
            variant_a_metrics=metrics_interactive,
            variant_b_name="Batch_NonInteractive_Mode",
            variant_b_metrics=metrics_batch,
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
