#!/usr/bin/env python
"""Phase 8 Central Research Evaluation, Ablation Studies, and Explainability Runner.

Executes:
1. Protocol verification & environment provenance recording.
2. 20-case benchmark evaluation across 6 architectural modes.
3. 5 controlled ablation studies (ASAA candidate budgets, LLM selection, coordination, refinement, clarification).
4. Multi-run deterministic reproducibility audit.
5. Evidence-grounded explainability dossier generation.
6. Statistical aggregation with 95% confidence intervals and feasibility classification.

Outputs saved to results/phase8_research_evaluation/.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import ezdxf
import numpy as np
import pydantic
import shapely

from app.evaluation.ablation import AblationStudyCoordinator
from app.evaluation.aggregation import MetricAggregator
from app.evaluation.benchmark import BenchmarkRegistry
from app.evaluation.metrics import MetricCalculator
from app.evaluation.models import (
    CaseEvaluationResult,
    EvaluationProtocolConfig,
)
from app.evaluation.reproducibility import ReproducibilityAuditor
from app.explainability.service import ExplainabilityService
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator


def compute_case_input_hashes() -> Dict[str, str]:
    """Compute SHA-256 hashes of all benchmark case inputs to verify provenance."""
    hashes = {}
    for c in BenchmarkRegistry.get_all_cases():
        raw = f"{c.case_id}|{c.name}|{c.brief.strip()}|{sorted(c.expected_properties.items())}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        hashes[c.case_id] = h
    return hashes


def build_protocol_config(experiment_id: str) -> EvaluationProtocolConfig:
    """Create authoritative protocol config capturing environment and dependency versions."""
    case_hashes = compute_case_input_hashes()
    case_ids = list(case_hashes.keys())

    deps = {
        "shapely": shapely.__version__,
        "ezdxf": ezdxf.__version__,
        "pydantic": pydantic.__version__,
        "numpy": np.__version__,
    }

    return EvaluationProtocolConfig(
        experiment_id=experiment_id,
        dataset_version="1.2.0",
        case_ids=case_ids,
        case_input_hashes=case_hashes,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        app_version="2.1.0",
        git_commit="phase8_head",
        python_version=platform.python_version(),
        os_platform=platform.platform(),
        environment_dependencies=deps,
        random_seed=42,
        asaa_candidate_budget=3,
        max_refinement_iterations=3,
        max_execution_steps=25,
        orchestration_mode="multi_agent",
        interactive=False,
        llm_provider="deterministic_fallback_or_configured",
        llm_model="gemini_or_mock",
        use_live_llm=False,
        scoring_version="v2.1",
        validator_version="v2.0",
    )


def run_phase8_evaluation() -> Dict[str, Any]:
    out_dir = Path("results/phase8_research_evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    experiment_id = f"exp_p8_{int(time.time())}"
    protocol = build_protocol_config(experiment_id)

    # Save protocol config
    with open(out_dir / "protocol_config.json", "w", encoding="utf-8") as f:
        json.dump(protocol.to_dict(), f, indent=2)

    orch = PlanForgeOrchestrator()
    all_cases = BenchmarkRegistry.get_all_cases()
    print(f"\n=======================================================")
    print(f"PlanForge Phase 8 Research Evaluation: {experiment_id}")
    print(f"Total Benchmark Cases: {len(all_cases)}")
    print(f"Python: {protocol.python_version} on {protocol.os_platform}")
    print(f"=======================================================\n")

    # -------------------------------------------------------------
    # 1. Comparative Evaluation across 5 Core Regression Cases
    # -------------------------------------------------------------
    core_case_ids = [
        "case_01_small_single_floor",
        "case_04_two_floor_family",
        "case_06_irregular_l_plot",
        "case_15_feasibility_edge",
        "case_16_infeasible_deficit",
    ]
    core_cases = [c for c in all_cases if c.case_id in core_case_ids]

    modes = [
        ("pipeline_baseline", {"mode": "pipeline", "interactive": False}),
        ("agentic_deterministic", {"mode": "agentic", "use_llm": False, "interactive": False}),
        ("agentic_llm", {"mode": "agentic", "use_llm": True, "enable_refinement": False, "interactive": False}),
        ("agentic_adaptive_refinement", {"mode": "agentic", "use_llm": True, "enable_refinement": True, "interactive": False}),
        ("hierarchical_multi_agent", {"mode": "multi_agent", "interactive": False}),
        ("interactive_clarification", {"mode": "multi_agent", "interactive": True}),
    ]

    comparative_results: List[Dict[str, Any]] = []

    print("--- Running Comparative Mode Evaluation ---")
    for case in core_cases:
        case_entry: Dict[str, Any] = {
            "case_id": case.case_id,
            "name": case.name,
            "modes": {},
        }
        for mode_name, mode_kwargs in modes:
            t0 = time.perf_counter()
            cfg = OrchestrationConfig(
                enable_rendering=False,
                enable_exports=False,
                output_dir=str(out_dir / "raw_runs" / mode_name / case.case_id),
                **mode_kwargs,
            )
            res = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg)
            dur_ms = (time.perf_counter() - t0) * 1000.0

            val_rep = res.validation_report
            score = val_rep.overall_score if val_rep else 0.0
            valid = val_rep.overall_valid if val_rep else False
            errs = val_rep.total_errors if val_rep else 0
            warns = val_rep.total_warnings if val_rep else 0

            case_entry["modes"][mode_name] = {
                "status": res.status,
                "is_valid": valid,
                "quality_score": round(score, 1),
                "errors": errs,
                "warnings": warns,
                "runtime_ms": round(dur_ms, 1),
                "clarification_questions": res.clarification_questions,
            }
        comparative_results.append(case_entry)
        print(f"  Completed comparative run for {case.case_id}")

    with open(out_dir / "comparative_modes_summary.json", "w", encoding="utf-8") as f:
        json.dump(comparative_results, f, indent=2)

    # -------------------------------------------------------------
    # 2. Comprehensive 20-Case Multi-Agent Evaluation & Metrics
    # -------------------------------------------------------------
    print("\n--- Running 20-Case Comprehensive Multi-Agent Evaluation ---")
    eval_case_results: List[CaseEvaluationResult] = []

    for case in all_cases:
        t0 = time.perf_counter()
        cfg = OrchestrationConfig(
            mode="multi_agent",
            interactive=False,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_eval" / case.case_id),
        )
        res = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg)
        dur_ms = (time.perf_counter() - t0) * 1000.0

        metrics = MetricCalculator.calculate_all(res, expected_props=case.expected_properties)
        timings = {k: getattr(v, "duration_ms", 0.0) for k, v in res.stage_records.items()}
        statuses = {k: getattr(v, "status").name for k, v in res.stage_records.items()}

        case_res = CaseEvaluationResult(
            case_id=case.case_id,
            name=case.name,
            tags=[t.value for t in case.tags],
            status=res.status,
            is_success=res.is_success,
            overall_valid=res.is_valid,
            error_message=res.error_message,
            metrics=metrics,
            stage_timings_ms=timings,
            stage_statuses=statuses,
        )
        eval_case_results.append(case_res)
        print(f"  {case.case_id}: status={case_res.status}, valid={case_res.overall_valid}, duration={dur_ms:.1f}ms")

    # Statistical Aggregation
    summary_stats = MetricAggregator.aggregate_cases(eval_case_results)
    with open(out_dir / "overall_metrics_table.json", "w", encoding="utf-8") as f:
        json.dump(summary_stats, f, indent=2)

    # -------------------------------------------------------------
    # 3. Controlled Ablation Studies
    # -------------------------------------------------------------
    print("\n--- Running Controlled Ablation Studies (A through E) ---")
    ablation_coord = AblationStudyCoordinator(seed=42)
    ablation_results: List[Dict[str, Any]] = []

    target_case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    l_shape_case = BenchmarkRegistry.get_case("case_06_irregular_l_plot")
    inf_case = BenchmarkRegistry.get_case("case_16_infeasible_deficit")

    # Ablation A: ASAA Candidate Budget (1 vs 3 candidates)
    if l_shape_case:
        ab_cand = ablation_coord.evaluate_candidate_budget_ablation(
            case=l_shape_case,
            orchestrator=orch,
            budgets=[1, 3],
            output_dir=str(out_dir / "ablation_raw" / "cand_budget"),
        )
        ablation_results.append(ab_cand.to_dict())
        print(f"  [Ablation A: Candidate Budget]: score delta={ab_cand.deltas.get('score_delta')}, runtime delta={ab_cand.deltas.get('runtime_delta_ms')}ms")

    # Ablation B: LLM Action Selection (LLM vs Rule-based)
    if target_case:
        ab_llm = ablation_coord.evaluate_llm_action_selection_ablation(
            case=target_case,
            orchestrator=orch,
            output_dir=str(out_dir / "ablation_raw" / "llm_selection"),
        )
        ablation_results.append(ab_llm.to_dict())
        print(f"  [Ablation B: LLM Selection]: score delta={ab_llm.deltas.get('score_delta')}, runtime delta={ab_llm.deltas.get('runtime_delta_ms')}ms")

    # Ablation C: Multi-Agent Coordination (Multi-Agent vs Pipeline)
    if target_case:
        ab_coord = ablation_coord.evaluate_multi_agent_coordination_ablation(
            case=target_case,
            orchestrator=orch,
            output_dir=str(out_dir / "ablation_raw" / "multi_agent"),
        )
        ablation_results.append(ab_coord.to_dict())
        print(f"  [Ablation C: Coordination]: score delta={ab_coord.deltas.get('score_delta')}, runtime delta={ab_coord.deltas.get('runtime_delta_ms')}ms")

    # Ablation D: Adaptive Refinement (With Refinement vs Without Refinement)
    if target_case:
        ab_ref = ablation_coord.evaluate_refinement_ablation(
            case=target_case,
            orchestrator=orch,
            output_dir=str(out_dir / "ablation_raw" / "refinement"),
        )
        ablation_results.append(ab_ref.to_dict())
        print(f"  [Ablation D: Refinement]: error reduction={ab_ref.deltas.get('error_reduction')}")

    # Ablation E: Clarification & Resumption (Interactive vs Batch)
    if inf_case:
        ab_clarif = ablation_coord.evaluate_clarification_ablation(
            case=inf_case,
            orchestrator=orch,
            output_dir=str(out_dir / "ablation_raw" / "clarification"),
        )
        ablation_results.append(ab_clarif.to_dict())
        print(f"  [Ablation E: Clarification]: clarification_triggered={ab_clarif.deltas.get('clarification_triggered')}, truthful_halt={ab_clarif.deltas.get('truthful_halt')}")

    with open(out_dir / "ablation_studies_summary.json", "w", encoding="utf-8") as f:
        json.dump(ablation_results, f, indent=2)

    # -------------------------------------------------------------
    # 4. Multi-Run Deterministic Reproducibility Audit
    # -------------------------------------------------------------
    print("\n--- Running Multi-Run Deterministic Reproducibility Audit ---")
    repro_auditor = ReproducibilityAuditor(runs_count=3, seed=42)
    repro_results = []
    for c_id in ["case_01_small_single_floor", "case_04_two_floor_family"]:
        c = BenchmarkRegistry.get_case(c_id)
        if c:
            rep = repro_auditor.audit_case(case=c, orchestrator=orch, output_dir=str(out_dir / "repro_raw"))
            repro_results.append(rep.to_dict())
            print(f"  {c_id}: identical across 3 runs = {rep.is_identical} (hashes={rep.hashes})")

    with open(out_dir / "reproducibility_summary.json", "w", encoding="utf-8") as f:
        json.dump(repro_results, f, indent=2)

    # -------------------------------------------------------------
    # 5. Evidence-Grounded Explainability Dossiers
    # -------------------------------------------------------------
    print("\n--- Generating Evidence-Grounded Explainability Dossiers ---")
    dossiers: List[Dict[str, Any]] = []
    for c_id in ["case_01_small_single_floor", "case_16_infeasible_deficit"]:
        c = BenchmarkRegistry.get_case(c_id)
        if not c:
            continue
        cfg = OrchestrationConfig(mode="multi_agent", interactive=True, enable_rendering=False, enable_exports=False)
        res = orch.generate(raw_brief=c.brief, project_name=c.name, config=cfg)
        dossier = ExplainabilityService.build_dossier_from_pipeline_result(res)
        dossiers.append(dossier.to_dict())
        print(f"  Generated dossier for {c_id}: status={dossier.status}")

    with open(out_dir / "explainability_dossiers.json", "w", encoding="utf-8") as f:
        json.dump(dossiers, f, indent=2)

    print("\n=======================================================")
    print(f"Phase 8 Research Evaluation Complete! Artifacts saved to: {out_dir}")
    print("=======================================================\n")

    return {
        "experiment_id": experiment_id,
        "protocol": protocol.to_dict(),
        "summary_stats": summary_stats,
        "comparative_modes": comparative_results,
        "ablation_results": ablation_results,
        "reproducibility_results": repro_results,
        "explainability_dossiers": dossiers,
    }


if __name__ == "__main__":
    run_phase8_evaluation()
