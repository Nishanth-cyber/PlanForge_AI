"""Unit tests for MetricCalculator and the 20 research evaluation metrics."""

from __future__ import annotations

import pytest
from app.evaluation.metrics import MetricCalculator
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.pipeline import PipelineResult


def test_metric_calculator_complete_pipeline_run():
    """Verify MetricCalculator computes all 20 metrics from a successful pipeline result."""
    orchestrator = PlanForgeOrchestrator()
    brief = """
    Single floor residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 260 sq ft adjacent to dining room
    - 1 dining room of 150 sq ft
    - 1 kitchen of 130 sq ft
    - 1 bedroom of 160 sq ft
    """

    cfg = OrchestrationConfig(
        enable_refinement=True,
        enable_rendering=False,
        enable_exports=False,
    )

    result = orchestrator.generate(brief, project_name="Metric Test", config=cfg)
    metrics = MetricCalculator.calculate_all(result)

    # 1. Requirement adherence
    assert "req_room_coverage" in metrics
    assert metrics["req_room_coverage"].is_available
    assert metrics["req_room_coverage"].value == 100.0

    # 2. Room count accuracy
    assert "room_count_accuracy" in metrics
    assert metrics["room_count_accuracy"].value >= 80.0

    # 3. Area satisfaction
    assert "area_min_compliance" in metrics
    assert metrics["area_min_compliance"].value >= 90.0

    # 4. Allocation Adjacency
    assert "allocation_adjacency_compliance" in metrics
    assert metrics["allocation_adjacency_compliance"].is_available

    # 7. Boundary compliance
    assert "boundary_compliance" in metrics
    assert metrics["boundary_compliance"].value == 100.0

    # 8. Overlap compliance
    assert "overlap_free" in metrics
    assert metrics["overlap_free"].value is True

    # 9. Connectivity
    assert "connectivity_rate" in metrics
    assert metrics["connectivity_rate"].value >= 90.0

    # 11. Staircase compliance on single-floor (should be NOT_AVAILABLE)
    assert "staircase_compliance" in metrics
    assert not metrics["staircase_compliance"].is_available
    assert "Single-floor" in (metrics["staircase_compliance"].unavailable_reason or "")

    # 12. Validation success
    assert "validation_success" in metrics
    assert metrics["validation_success"].value is True

    # 14. Diversity on single alternative (should be NOT_AVAILABLE)
    assert "diversity_mean_distance" in metrics
    assert not metrics["diversity_mean_distance"].is_available

    # 16. Explainability completeness
    assert "trace_stage_coverage" in metrics
    assert metrics["trace_stage_coverage"].value >= 60.0

    # 17. Trace fabrication safety
    assert "trace_no_fabrication_audit" in metrics
    assert metrics["trace_no_fabrication_audit"].value is True

    # 18. Computational performance
    assert "timing_total_ms" in metrics
    assert metrics["timing_total_ms"].value > 0

    # 19. ASAA performance
    assert "asaa_duration_ms" in metrics
    assert metrics["asaa_duration_ms"].value >= 0


def test_metric_calculator_handles_missing_artifacts_gracefully():
    """Verify MetricCalculator handles partial or empty results without crashing or fabricating numbers."""
    empty_result = PipelineResult(
        project_id="empty_proj",
        status="incomplete_requirements",
    )

    metrics = MetricCalculator.calculate_all(empty_result)

    # Should safely record NOT_AVAILABLE for missing artifacts
    assert not metrics["req_room_coverage"].is_available
    assert not metrics["area_min_compliance"].is_available
    assert not metrics["allocation_adjacency_compliance"].is_available
    assert not metrics["boundary_compliance"].is_available
    assert not metrics["trace_completeness"].is_available
