"""Unit tests for evaluation reporting, CSV export, and plot generation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from app.evaluation.aggregation import MetricAggregator
from app.evaluation.models import (
    AblationResult,
    CaseEvaluationResult,
    EvaluationConfig,
    ExperimentRun,
    MetricValue,
)
from app.evaluation.plotting import EvaluationPlotter
from app.evaluation.reporting import EvaluationReporter


def test_reporting_exports_json_csv_and_markdown(tmp_path: Path):
    """Verify EvaluationReporter generates valid JSON, CSV, and Markdown files."""
    case_res = CaseEvaluationResult(
        case_id="test_case_1",
        name="Test Case 1",
        tags=["SINGLE_FLOOR"],
        status="completed",
        is_success=True,
        overall_valid=True,
        metrics={
            "req_room_coverage": MetricValue("req_room_coverage", 100.0, "%"),
            "area_preferred_mae": MetricValue("area_preferred_mae", 2.5, "m²"),
        },
        stage_timings_ms={"REQUIREMENTS": 12.0, "ASAA": 25.0},
    )

    ab_res = AblationResult(
        ablation_id="ab_1",
        case_id="test_case_1",
        variant_a_name="Full_ASAA",
        variant_a_metrics={"total_execution_ms": 150.0},
        variant_b_name="Baseline",
        variant_b_metrics={"total_execution_ms": 120.0},
        deltas={"error_reduction": 2.0},
    )

    summary = MetricAggregator.aggregate_cases([case_res])

    run = ExperimentRun(
        run_id="test_run",
        timestamp="2026-09-19T00:00:00Z",
        config=EvaluationConfig(output_dir=str(tmp_path)),
        case_results=[case_res],
        ablation_results=[ab_res],
        summary_metrics=summary,
    )

    paths = EvaluationReporter.export_all(run, tmp_path)

    assert Path(paths["benchmark_results_json"]).exists()
    assert Path(paths["metric_summary_json"]).exists()
    assert Path(paths["ablation_results_json"]).exists()
    assert Path(paths["benchmark_metrics_csv"]).exists()
    assert Path(paths["ablation_metrics_csv"]).exists()
    assert Path(paths["performance_metrics_csv"]).exists()
    assert Path(paths["markdown_report"]).exists()

    # Verify JSON content
    with open(paths["benchmark_results_json"], encoding="utf-8") as f:
        data = json.load(f)
        assert data["run_id"] == "test_run"
        assert len(data["case_results"]) == 1

    # Verify Markdown report content
    with open(paths["markdown_report"], encoding="utf-8") as f:
        md_text = f.read()
        assert "PlanForge AI — Research Evaluation & Benchmarking Report" in md_text
        assert "test_case_1" in md_text


def test_plotter_generates_png_figures(tmp_path: Path):
    """Verify EvaluationPlotter generates valid non-empty PNG figures without GUI errors."""
    summary = {
        "metrics": {
            "req_room_coverage": {"mean": 100.0},
            "area_min_compliance": {"mean": 98.0},
            "allocation_adjacency_compliance": {"mean": 90.0},
            "boundary_compliance": {"mean": 100.0},
            "connectivity_rate": {"mean": 100.0},
            "timing_requirements_ms": {"mean": 10.0},
            "timing_planning_ms": {"mean": 15.0},
            "timing_asaa_ms": {"mean": 30.0},
        }
    }

    ab_res = [
        AblationResult(
            ablation_id="ab_asaa_1",
            case_id="case_1",
            variant_a_name="Full_ASAA",
            variant_a_metrics={"allocation_score": 92.0},
            variant_b_name="Baseline",
            variant_b_metrics={"allocation_score": 50.0},
        ),
        AblationResult(
            ablation_id="ab_refinement_1",
            case_id="case_1",
            variant_a_name="With_Refinement",
            variant_a_metrics={"validation_error_count": 0},
            variant_b_name="Without_Refinement",
            variant_b_metrics={"validation_error_count": 2},
        ),
    ]

    plots = EvaluationPlotter.plot_all(summary, ab_res, tmp_path)
    assert len(plots) >= 3
    for p in plots:
        f = Path(p)
        assert f.exists()
        assert f.stat().st_size > 1000  # Non-trivial image size
