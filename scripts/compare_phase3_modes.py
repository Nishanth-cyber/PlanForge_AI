#!/usr/bin/env python
"""Comparative benchmark evaluation between Pipeline Mode and Agentic Mode across Phase 2 cases."""

import json
import time
from pathlib import Path

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


def run_comparison():
    orch = PlanForgeOrchestrator()
    out_dir = Path("results/phase3_comparison")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "pipeline_mode": {},
        "agentic_mode": {},
        "comparison_table": [],
    }

    for case_id in TEST_CASES:
        case = BenchmarkRegistry.get_case(case_id)
        if not case:
            continue

        print(f"Evaluating {case_id}...")

        # 1. Pipeline Mode
        t0 = time.perf_counter()
        cfg_pipe = OrchestrationConfig(
            mode="pipeline",
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_pipe" / case_id),
        )
        res_pipe = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_pipe)
        pipe_ms = (time.perf_counter() - t0) * 1000.0

        # 2. Agentic Mode
        t0 = time.perf_counter()
        cfg_agent = OrchestrationConfig(
            mode="agentic",
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_agent" / case_id),
        )
        res_agent = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_agent)
        agent_ms = (time.perf_counter() - t0) * 1000.0

        score_pipe = res_pipe.validation_report.overall_score if res_pipe.validation_report else 0.0
        score_agent = res_agent.validation_report.overall_score if res_agent.validation_report else 0.0

        row = {
            "case_id": case_id,
            "pipeline": {
                "status": res_pipe.status,
                "is_valid": res_pipe.is_valid,
                "score": round(score_pipe, 1),
                "duration_ms": round(pipe_ms, 1),
                "error": res_pipe.error_message,
            },
            "agentic": {
                "status": res_agent.status,
                "is_valid": res_agent.is_valid,
                "score": round(score_agent, 1),
                "duration_ms": round(agent_ms, 1),
                "decisions_count": len(res_agent.decisions or []),
                "error": res_agent.error_message,
                "infeasibility_evidence": (res_agent.agentic_state or {}).get("infeasibility_evidence", []),
            },
        }
        results["comparison_table"].append(row)

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n=== PHASE 3 COMPARISON COMPLETE ===")
    for r in results["comparison_table"]:
        print(
            f"{r['case_id']:30} | "
            f"Pipe: {r['pipeline']['status']:7} ({r['pipeline']['score']:4.1f} score, {r['pipeline']['duration_ms']:5.1f}ms) | "
            f"Agent: {r['agentic']['status']:7} ({r['agentic']['score']:4.1f} score, {r['agentic']['duration_ms']:5.1f}ms, {r['agentic']['decisions_count']} dec)"
        )


if __name__ == "__main__":
    run_comparison()
