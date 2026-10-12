#!/usr/bin/env python
"""Three-way comparative evaluation across Phase 2 benchmark cases:
1. Original Pipeline Mode
2. Phase 3 Agentic Mode (Deterministic Policy)
3. Phase 4 Agentic Mode (Configured LLM Action Selector)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

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


def evaluate_modes() -> Dict[str, Any]:
    orch = PlanForgeOrchestrator()
    out_dir = Path("results/phase4_evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "evaluation_title": "Phase 4 Three-Way Mode Comparison",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases_evaluated": TEST_CASES,
        "modes": ["pipeline", "agentic_deterministic", "agentic_llm"],
        "comparison_table": [],
    }

    for case_id in TEST_CASES:
        case = BenchmarkRegistry.get_case(case_id)
        if not case:
            continue

        print(f"Evaluating {case_id} across all 3 modes...")

        # -------------------------------------------------------------
        # 1. Pipeline Mode Baseline
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # 2. Phase 3 Agentic Mode (Deterministic Policy: use_llm=False)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        cfg_det = OrchestrationConfig(
            mode="agentic",
            use_llm=False,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_det" / case_id),
        )
        res_det = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_det)
        det_ms = (time.perf_counter() - t0) * 1000.0
        val_det = res_det.validation_report
        state_det = res_det.agentic_state or {}
        decisions_det = res_det.decisions or []

        # -------------------------------------------------------------
        # 3. Phase 4 Agentic Mode (LLM Action Selector: use_llm=True)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        cfg_llm = OrchestrationConfig(
            mode="agentic",
            use_llm=True,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_llm" / case_id),
        )
        res_llm = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_llm)
        llm_ms = (time.perf_counter() - t0) * 1000.0
        val_llm = res_llm.validation_report
        state_llm = res_llm.agentic_state or {}
        decisions_llm = res_llm.decisions or []

        # Tally decision sources for LLM mode
        sources_count = {}
        for d in decisions_llm:
            src = d.get("source", "unknown")
            sources_count[src] = sources_count.get(src, 0) + 1

        budget_llm = state_llm.get("budget", {})

        row = {
            "case_id": case_id,
            "case_name": case.name,
            "pipeline": {
                "status": res_pipe.status,
                "is_valid": res_pipe.is_valid,
                "score": round(val_pipe.overall_score, 1) if val_pipe else 0.0,
                "hard_errors": val_pipe.total_errors if val_pipe else 0,
                "duration_ms": round(pipe_ms, 1),
                "error": res_pipe.error_message,
            },
            "agentic_deterministic": {
                "status": res_det.status,
                "is_valid": res_det.is_valid,
                "score": round(val_det.overall_score, 1) if val_det else 0.0,
                "hard_errors": val_det.total_errors if val_det else 0,
                "duration_ms": round(det_ms, 1),
                "decisions_count": len(decisions_det),
                "tool_calls_count": len(state_det.get("tool_calls", [])),
                "error": res_det.error_message,
                "infeasibility_evidence": state_det.get("infeasibility_evidence", []),
            },
            "agentic_llm": {
                "status": res_llm.status,
                "is_valid": res_llm.is_valid,
                "score": round(val_llm.overall_score, 1) if val_llm else 0.0,
                "hard_errors": val_llm.total_errors if val_llm else 0,
                "duration_ms": round(llm_ms, 1),
                "decisions_count": len(decisions_llm),
                "decision_sources": sources_count,
                "tool_calls_count": len(state_llm.get("tool_calls", [])),
                "llm_calls_count": budget_llm.get("llm_calls_used", 0),
                "fallback_count": sources_count.get("fallback", 0),
                "error": res_llm.error_message,
                "infeasibility_evidence": state_llm.get("infeasibility_evidence", []),
            },
        }
        summary["comparison_table"].append(row)

    summary_file = out_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved evaluation summary to: {summary_file}")
    print("\n" + "=" * 95)
    print(f"{'Case ID':30} | {'Pipeline':18} | {'Agentic Det':20} | {'Agentic LLM':20}")
    print("=" * 95)
    for r in summary["comparison_table"]:
        p_str = f"{r['pipeline']['status']} ({r['pipeline']['score']}pts)"
        d_str = f"{r['agentic_deterministic']['status']} ({r['agentic_deterministic']['score']}pts)"
        l_str = f"{r['agentic_llm']['status']} ({r['agentic_llm']['score']}pts)"
        print(f"{r['case_id']:30} | {p_str:18} | {d_str:20} | {l_str:20}")
    print("=" * 95)

    return summary


if __name__ == "__main__":
    evaluate_modes()
