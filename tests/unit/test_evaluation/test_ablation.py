"""Unit tests for controlled ablation experiments."""

from __future__ import annotations

import pytest
from app.evaluation.ablation import AblationStudyCoordinator
from app.evaluation.benchmark import BenchmarkRegistry
from app.orchestration.orchestrator import PlanForgeOrchestrator


def test_controlled_asaa_ablation(tmp_path):
    """Verify controlled ASAA ablation runs full vs baseline on identical brief."""
    coordinator = AblationStudyCoordinator(seed=42)
    orchestrator = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    res = coordinator.evaluate_asaa_ablation(
        case=case,
        full_orchestrator=orchestrator,
        output_dir=str(tmp_path / "ablation_asaa"),
    )

    assert res.variant_a_name == "Full_PlanForge_ASAA"
    assert res.variant_b_name == "Without_ASAA_Baseline"
    assert "total_allocated_area_sqm" in res.variant_a_metrics
    assert "total_allocated_area_sqm" in res.variant_b_metrics
    assert res.variant_a_metrics["is_success"] is True
    assert res.variant_b_metrics["is_success"] is True


def test_controlled_refinement_ablation(tmp_path):
    """Verify controlled refinement ablation compares with vs without refinement."""
    coordinator = AblationStudyCoordinator(seed=42)
    orchestrator = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    res = coordinator.evaluate_refinement_ablation(
        case=case,
        orchestrator=orchestrator,
        output_dir=str(tmp_path / "ablation_refine"),
    )

    assert res.variant_a_name == "With_Refinement"
    assert res.variant_b_name == "Without_Refinement"
    assert "error_reduction" in res.deltas


def test_controlled_diversity_ablation(tmp_path):
    """Verify controlled diversity ablation compares single vs multi alternatives."""
    coordinator = AblationStudyCoordinator(seed=42)
    orchestrator = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_02_medium_single_floor")
    assert case is not None

    res = coordinator.evaluate_diversity_ablation(
        case=case,
        orchestrator=orchestrator,
        counts=[1, 2],
        output_dir=str(tmp_path / "ablation_div"),
    )

    assert "Multi_Alternatives_2" in res.variant_a_name
    assert "Single_Alternative_1" in res.variant_b_name
    assert res.deltas["alternatives_count_delta"] >= 0.0
