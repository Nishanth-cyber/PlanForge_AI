#!/usr/bin/env python
"""Phase 5 Comparative Evaluation across 5 benchmark cases:
1. Pipeline Baseline Mode
2. Phase 3 Agentic Mode (Deterministic Policy)
3. Phase 4 Agentic Mode (LLM Action Selector)
4. Phase 5 Adaptive Refinement & Replanning Mode

Outputs saved to results/phase5_evaluation/summary.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from app.evaluation.benchmark import BenchmarkRegistry
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator

TEST_CASES = [
    "case_01_small_single_floor",
    "case_04_two_floor_family",
    "case_06_irregular_l_plot",
    "case_15_feasibility_edge",
    "case_16_infeasible_deficit",
]


def evaluate_phase5() -> Dict[str, Any]:
    orch = PlanForgeOrchestrator()
    out_dir = Path("results/phase5_evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "evaluation_title": "Phase 5 Adaptive Refinement and Strategic Replanning Comparison",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases_evaluated": TEST_CASES,
        "modes": ["pipeline", "agentic_phase3_det", "agentic_phase4_llm", "agentic_phase5_adaptive"],
        "comparison_table": [],
    }

    for case_id in TEST_CASES:
        case = BenchmarkRegistry.get_case(case_id)
        if not case:
            continue

        print(f"Evaluating {case_id} across baseline and adaptive modes...")

        # 1. Pipeline Baseline Mode
        t0 = time.perf_counter()
        cfg_pipe = OrchestrationConfig(
            mode="pipeline",
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_pipe" / case_id),
        )
        res_pipe = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_pipe)
        pipe_ms = (time.perf_counter() - t0) * 1000.0
        val_pipe = res_pipe.validation_report

        # 2. Phase 3 Deterministic Agentic Mode
        t0 = time.perf_counter()
        cfg_p3 = OrchestrationConfig(
            mode="agentic",
            use_llm=False,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p3" / case_id),
        )
        res_p3 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p3)
        p3_ms = (time.perf_counter() - t0) * 1000.0
        val_p3 = res_p3.validation_report

        # 3. Phase 4 LLM Agentic Mode
        t0 = time.perf_counter()
        cfg_p4 = OrchestrationConfig(
            mode="agentic",
            use_llm=True,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p4" / case_id),
        )
        res_p4 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p4)
        p4_ms = (time.perf_counter() - t0) * 1000.0
        val_p4 = res_p4.validation_report

        # 4. Phase 5 Adaptive Refinement Mode (with Candidate Manager & Adaptive Replanning)
        t0 = time.perf_counter()
        cfg_p5 = OrchestrationConfig(
            mode="agentic",
            use_llm=True,
            enable_refinement=True,
            max_refinement_iterations=5,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p5" / case_id),
        )
        res_p5 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p5)
        p5_ms = (time.perf_counter() - t0) * 1000.0
        val_p5 = res_p5.validation_report
        state_p5 = res_p5.agentic_state or {}
        cand_history_p5 = state_p5.get("candidate_history", [])
        events_p5 = state_p5.get("events", [])

        # Candidate breakdown
        accepted_cands = sum(1 for c in cand_history_p5 if c.get("acceptance_decision") in ("accepted_best", "accepted_progress"))
        rejected_cands = sum(1 for c in cand_history_p5 if "rejected" in str(c.get("acceptance_decision", "")))
        regression_rejections = sum(1 for c in cand_history_p5 if c.get("acceptance_decision") == "rejected_regression")

        # Decision / replanning metrics
        strategy_changes = sum(1 for e in events_p5 if e.get("type") in ("strategy_updated", "replanning_initiated"))
        refinements_attempted = sum(1 for tc in state_p5.get("tool_calls", []) if tc.get("tool") == "refine_design")
        reallocations_attempted = sum(1 for tc in state_p5.get("tool_calls", []) if tc.get("tool") == "allocate_spatial_regions")
        llm_calls_used = state_p5.get("budget", {}).get("llm_calls_used", 0)
        tool_calls_used = state_p5.get("budget", {}).get("tool_calls_used", 0)

        # Infeasibility detection
        is_infeasible_expected = (case_id == "case_16_infeasible_deficit")
        is_infeasible_detected_p5 = (res_p5.status == "failed" and state_p5.get("run_status") == "infeasible")

        record = {
            "case_id": case_id,
            "case_name": case.name,
            "expected_infeasible": is_infeasible_expected,
            "pipeline": {
                "success": res_pipe.is_success,
                "valid": bool(val_pipe.overall_valid if val_pipe else False),
                "score": round(val_pipe.overall_score, 1) if val_pipe else None,
                "hard_errors": val_pipe.total_errors if val_pipe else 0,
                "warnings": val_pipe.total_warnings if val_pipe else 0,
                "duration_ms": round(pipe_ms, 1),
            },
            "phase3_det": {
                "success": res_p3.is_success,
                "valid": bool(val_p3.overall_valid if val_p3 else False),
                "score": round(val_p3.overall_score, 1) if val_p3 else None,
                "hard_errors": val_p3.total_errors if val_p3 else 0,
                "duration_ms": round(p3_ms, 1),
            },
            "phase4_llm": {
                "success": res_p4.is_success,
                "valid": bool(val_p4.overall_valid if val_p4 else False),
                "score": round(val_p4.overall_score, 1) if val_p4 else None,
                "hard_errors": val_p4.total_errors if val_p4 else 0,
                "duration_ms": round(p4_ms, 1),
            },
            "phase5_adaptive": {
                "success": res_p5.is_success,
                "valid": bool(val_p5.overall_valid if val_p5 else False),
                "score": round(val_p5.overall_score, 1) if val_p5 else None,
                "hard_errors": val_p5.total_errors if val_p5 else 0,
                "warnings": val_p5.total_warnings if val_p5 else 0,
                "duration_ms": round(p5_ms, 1),
                "infeasibility_correctly_handled": is_infeasible_detected_p5 if is_infeasible_expected else (res_p5.is_success),
                "total_candidates": len(cand_history_p5),
                "accepted_candidates": accepted_cands,
                "rejected_candidates": rejected_cands,
                "regression_rejections": regression_rejections,
                "refinements_attempted": refinements_attempted,
                "reallocations_attempted": reallocations_attempted,
                "strategy_changes": strategy_changes,
                "llm_calls_used": llm_calls_used,
                "tool_calls_used": tool_calls_used,
                "best_candidate_id": state_p5.get("best_candidate", {}).get("id") if state_p5.get("best_candidate") else None,
            },
        }
        summary["comparison_table"].append(record)
        print(f"  -> Pipeline: valid={record['pipeline']['valid']} (score={record['pipeline']['score']})")
        print(f"  -> Phase 4 LLM: valid={record['phase4_llm']['valid']} (score={record['phase4_llm']['score']})")
        print(f"  -> Phase 5 Adaptive: valid={record['phase5_adaptive']['valid']} (score={record['phase5_adaptive']['score']}, cands={len(cand_history_p5)}, reg_rej={regression_rejections})")

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nPhase 5 evaluation completed. Results written to {out_dir / 'summary.json'}")
    return summary


if __name__ == "__main__":
    evaluate_phase5()
