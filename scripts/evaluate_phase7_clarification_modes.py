#!/usr/bin/env python
"""Phase 7 Benchmark Evaluation: Interactive Agentic Clarification & Resumable Generation.

Evaluates the 5 benchmark cases across:
1. Pipeline Baseline Mode (mode="pipeline")
2. Phase 6 Multi-Agent Mode (mode="multi_agent", interactive=False)
3. Phase 7 Interactive Multi-Agent Mode (mode="multi_agent", interactive=True)
   - Evaluates whether feasible cases proceed without unnecessary clarification.
   - Evaluates whether infeasible cases pause with WAITING_FOR_CLARIFICATION.
   - Evaluates interactive resolution & workflow resumption on case_16.

Outputs saved to results/phase7_evaluation/summary.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from app.evaluation.benchmark import BenchmarkRegistry
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.hierarchical import HierarchicalOrchestrator
from app.agentic.state import RunStatus

TEST_CASES = [
    "case_01_small_single_floor",
    "case_04_two_floor_family",
    "case_06_irregular_l_plot",
    "case_15_feasibility_edge",
    "case_16_infeasible_deficit",
]


def evaluate_phase7() -> Dict[str, Any]:
    orch = PlanForgeOrchestrator()
    out_dir = Path("results/phase7_evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "evaluation_title": "Phase 7 Interactive Clarification & Resumable Workflow Benchmark",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases_evaluated": TEST_CASES,
        "modes": [
            "pipeline_baseline",
            "phase6_multi_agent_batch",
            "phase7_interactive_multi_agent",
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

        # 2. Phase 6 Multi-Agent Batch Mode (interactive=False)
        t0 = time.perf_counter()
        cfg_p6 = OrchestrationConfig(
            mode="multi_agent",
            interactive=False,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p6" / case_id),
        )
        res_p6 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p6)
        p6_ms = (time.perf_counter() - t0) * 1000.0
        val_p6 = res_p6.validation_report

        # 3. Phase 7 Interactive Multi-Agent Mode (interactive=True)
        t0 = time.perf_counter()
        cfg_p7 = OrchestrationConfig(
            mode="multi_agent",
            interactive=True,
            enable_rendering=False,
            enable_exports=False,
            output_dir=str(out_dir / "raw_p7" / case_id),
        )
        res_p7 = orch.generate(raw_brief=case.brief, project_name=case.name, config=cfg_p7)
        p7_ms = (time.perf_counter() - t0) * 1000.0
        val_p7 = res_p7.validation_report

        clarif_triggered = res_p7.status == "waiting_for_clarification"
        resumed_res = None
        resume_ms = 0.0

        # For case_16 (infeasible deficit), simulate user answering clarification and resuming
        if clarif_triggered and res_p7.clarification_questions:
            print(f"  [Phase 7] Interactive Clarification Triggered: {res_p7.clarification_questions[0]}")
            # If case_16, test interactive resolution:
            if case_id == "case_16_infeasible_deficit":
                print("  [Phase 7] Simulating user response: Authorizing plot expansion to relieve deficit...")
                t_res_0 = time.perf_counter()
                hier_orch = HierarchicalOrchestrator(registry=orch.tool_registry, interactive=True)
                st = hier_orch.run(project_id=f"p7_interactive_{case_id}", raw_brief=case.brief)
                if st.pending_clarification:
                    req_id = st.pending_clarification.request_id
                    # Select plot expansion (width 20m, length 20m) to relieve 112.6 sqm deficit
                    hier_orch.apply_clarification_response(
                        state=st,
                        request_id=req_id,
                        selected_option_id="expand_plot_depth",
                        numeric_overrides={"plot_width": 20.0, "plot_length": 20.0},
                    )
                    res_ok, _, resumed_st = hier_orch.resume(st)
                    resume_ms = (time.perf_counter() - t_res_0) * 1000.0
                    resumed_res = orch._create_result_from_agentic_state(
                        project_state=resumed_st,
                        project_id=resumed_st.project_id,
                        project_name=case.name,
                        cfg=cfg_p7,
                    )
                    print(f"  [Phase 7] Workflow Resumed Status: {resumed_res.status} in {resume_ms:.1f}ms")

        entry = {
            "case_id": case_id,
            "name": case.name,
            "pipeline": {
                "status": res_pipe.status,
                "score": val_pipe.overall_score if val_pipe else 0.0,
                "hard_errors": val_pipe.total_errors if val_pipe else 0,
                "runtime_ms": round(pipe_ms, 1),
            },
            "phase6_multi_agent": {
                "status": res_p6.status,
                "score": val_p6.overall_score if val_p6 else 0.0,
                "hard_errors": val_p6.total_errors if val_p6 else 0,
                "runtime_ms": round(p6_ms, 1),
            },
            "phase7_interactive": {
                "status": res_p7.status,
                "score": val_p7.overall_score if val_p7 else 0.0,
                "hard_errors": val_p7.total_errors if val_p7 else 0,
                "runtime_ms": round(p7_ms, 1),
                "clarification_triggered": clarif_triggered,
                "clarification_questions": res_p7.clarification_questions,
                "resumed_result": {
                    "status": resumed_res.status,
                    "score": resumed_res.validation_report.overall_score if resumed_res and resumed_res.validation_report else 0.0,
                    "hard_errors": resumed_res.validation_report.total_errors if resumed_res and resumed_res.validation_report else 0,
                    "resume_ms": round(resume_ms, 1),
                } if resumed_res else None,
            },
        }
        summary["comparison_table"].append(entry)

        print(f"Pipeline: status={entry['pipeline']['status']}, score={entry['pipeline']['score']}, {entry['pipeline']['runtime_ms']}ms")
        print(f"Phase 6:  status={entry['phase6_multi_agent']['status']}, score={entry['phase6_multi_agent']['score']}, {entry['phase6_multi_agent']['runtime_ms']}ms")
        print(f"Phase 7:  status={entry['phase7_interactive']['status']}, score={entry['phase7_interactive']['score']}, {entry['phase7_interactive']['runtime_ms']}ms (clarif={clarif_triggered})")

    out_file = out_dir / "summary.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=======================================================")
    print(f"Phase 7 Evaluation complete! Saved to {out_file}")
    print(f"=======================================================")
    return summary


if __name__ == "__main__":
    evaluate_phase7()
