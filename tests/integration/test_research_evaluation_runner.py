"""End-to-end integration tests for BenchmarkRunner and the Phase 13 evaluation framework."""

from __future__ import annotations

from pathlib import Path
import pytest
from app.evaluation.models import EvaluationConfig
from app.evaluation.runner import BenchmarkRunner


def test_end_to_end_benchmark_runner(tmp_path: Path):
    """Verify BenchmarkRunner executes full evaluation pipeline, ablations, reports, and plots."""
    config = EvaluationConfig(
        benchmark_case_ids=[
            "case_01_small_single_floor",
            "case_04_two_floor_family",
            "case_16_infeasible_deficit",
        ],
        output_dir=str(tmp_path / "eval_out"),
        run_baseline=True,
        run_ablation=True,
        run_reproducibility=True,
        reproducibility_runs=2,
        export_plots=True,
    )

    runner = BenchmarkRunner(config=config)
    run = runner.run()

    # 1. Verify case results
    assert len(run.case_results) == 3
    c_small = next(c for c in run.case_results if c.case_id == "case_01_small_single_floor")
    c_two = next(c for c in run.case_results if c.case_id == "case_04_two_floor_family")
    c_inf = next(c for c in run.case_results if c.case_id == "case_16_infeasible_deficit")

    # Small house passes
    assert c_small.is_success is True
    assert c_small.metrics["req_room_coverage"].value == 100.0

    # Two-floor house passes with multi-floor staircase
    assert c_two.is_success is True
    assert c_two.metrics["staircase_compliance"].is_available
    assert c_two.metrics["staircase_compliance"].value == 100.0

    # Infeasible program fails gracefully without crash or fabricated plan
    assert c_inf.is_success is False
    assert c_inf.overall_valid is False

    # 2. Verify ablations ran
    assert len(run.ablation_results) > 0

    # 3. Verify reproducibility ran
    assert len(run.reproducibility_results) > 0
    assert run.reproducibility_results[0].is_identical is True

    # 4. Verify all output files generated on disk
    out_dir = Path(config.output_dir)
    assert (out_dir / "benchmark_results.json").exists()
    assert (out_dir / "metric_summary.json").exists()
    assert (out_dir / "ablation_results.json").exists()
    assert (out_dir / "reproducibility_results.json").exists()
    assert (out_dir / "benchmark_metrics.csv").exists()
    assert (out_dir / "ablation_metrics.csv").exists()
    assert (out_dir / "performance_metrics.csv").exists()
    assert (out_dir / "RESEARCH_EVALUATION_REPORT.md").exists()

    # Verify plots generated
    plot_dir = out_dir / "plots"
    assert plot_dir.exists()
    assert len(list(plot_dir.glob("*.png"))) >= 2
