#!/usr/bin/env python
"""Phase 6 Comparative Evaluation across 5 benchmark cases:
1. Pipeline Baseline Mode
2. Phase 3 Agentic Mode (Deterministic Policy)
3. Phase 4 Agentic Mode (LLM Action Selector)
4. Phase 5 Adaptive Refinement & Replanning Mode
5. Phase 6 Hybrid Hierarchical Multi-Agent Coordinated Mode

Outputs saved to results/phase6_evaluation/summary.json.
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


def evaluate_phase6() -> Dict[str, Any]:
    orch = PlanForgeOrchestrator()
    out_dir = Path("results/phase6_evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "evaluation_title": "Phase 6 Hybrid Hierarchical Multi-Agent Coordination Comparison",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases_evaluated": TEST_CASES,
        "modes": [
            "pipeline",
            "agentic_phase3_det",
            "agentic_phase4_llm",
            "agentic_phase5_adaptive",
            "agentic_phase6_multi_agent",
        ],
        "comparison_table": [],
    }

    for case_id in TEST_CASES:
        case = BenchmarkRegistry.get_case(case_id)
        if not case:
            continue

        print(f"\n=======================================================")
        print(f"Evaluating {case_id}: {case.name}")
        print(f"=======================================================")

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
            enable_refinement=False,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p4" / case_id),
        )
        res_p4 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p4)
        p4_ms = (time.perf_counter() - t0) * 1000.0
        val_p4 = res_p4.validation_report

        # 4. Phase 5 Adaptive Refinement Mode
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

        # 5. Phase 6 Hybrid Hierarchical Multi-Agent Coordinated Mode
        t0 = time.perf_counter()
        cfg_p6 = OrchestrationConfig(
            mode="multi_agent",
            use_llm=True,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p6" / case_id),
        )
        res_p6 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p6)
        p6_ms = (time.perf_counter() - t0) * 1000.0
        val_p6 = res_p6.validation_report

        def _extract_metrics(res, val_rep, dur_ms):
            is_valid = bool(val_rep.overall_valid) if val_rep else (res.is_success and res.status == "completed")
            score = round(val_rep.overall_score, 1) if (val_rep and getattr(val_rep, "overall_score", None) is not None) else (100.0 if res.is_success else 0.0)
            hard_errors = val_rep.total_errors if val_rep else 0
            warnings = val_rep.total_warnings if val_rep else 0
            tools_used = len(res.agentic_state.get("tool_calls", [])) if getattr(res, "agentic_state", None) else 0
            decisions_count = len(getattr(res, "decisions", []) or [])
            events_count = len(res.agentic_state.get("events", [])) if getattr(res, "agentic_state", None) else 0

            return {
                "status": res.status,
                "is_valid": is_valid,
                "score": score,
                "hard_errors": hard_errors,
                "warnings": warnings,
                "tool_calls_count": tools_used,
                "decisions_count": decisions_count,
                "events_count": events_count,
                "duration_ms": round(dur_ms, 1),
            }

        pipe_m = _extract_metrics(res_pipe, val_pipe, pipe_ms)
        p3_m = _extract_metrics(res_p3, val_p3, p3_ms)
        p4_m = _extract_metrics(res_p4, val_p4, p4_ms)
        p5_m = _extract_metrics(res_p5, val_p5, p5_ms)
        p6_m = _extract_metrics(res_p6, val_p6, p6_ms)

        print(f"  Pipeline Mode:        Status={pipe_m['status']}, Valid={pipe_m['is_valid']}, Score={pipe_m['score']}, Latency={pipe_m['duration_ms']}ms")
        print(f"  Phase 3 Det Agent:    Status={p3_m['status']}, Valid={p3_m['is_valid']}, Score={p3_m['score']}, Latency={p3_m['duration_ms']}ms")
        print(f"  Phase 4 LLM Agent:    Status={p4_m['status']}, Valid={p4_m['is_valid']}, Score={p4_m['score']}, Latency={p4_m['duration_ms']}ms")
        print(f"  Phase 5 Adaptive:     Status={p5_m['status']}, Valid={p5_m['is_valid']}, Score={p5_m['score']}, Latency={p5_m['duration_ms']}ms")
        print(f"  Phase 6 Multi-Agent:  Status={p6_m['status']}, Valid={p6_m['is_valid']}, Score={p6_m['score']}, Latency={p6_m['duration_ms']}ms, Events={p6_m['events_count']}")

        summary["comparison_table"].append({
            "case_id": case_id,
            "case_name": case.name,
            "pipeline": pipe_m,
            "phase3": p3_m,
            "phase4": p4_m,
            "phase5": p5_m,
            "phase6": p6_m,
        })

    # Save summary report
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[SUCCESS] Phase 6 Multi-Agent Evaluation summary saved to {summary_path}")
    return summary


if __name__ == "__main__":
    evaluate_phase6()
