"""Unit tests for benchmark case models and dataset integrity."""

from __future__ import annotations

import pytest
from app.evaluation.benchmark import BENCHMARK_CASES, BenchmarkCategory, BenchmarkRegistry
from app.evaluation.models import BenchmarkCase


def test_benchmark_dataset_completeness():
    """Verify that the benchmark dataset contains all 16 required canonical cases."""
    assert len(BENCHMARK_CASES) >= 16

    cases = BenchmarkRegistry.get_all_cases()
    assert len(cases) >= 16

    # Verify key case IDs exist
    expected_ids = [
        "case_01_small_single_floor",
        "case_02_medium_single_floor",
        "case_03_large_single_floor",
        "case_04_two_floor_family",
        "case_05_three_floor_townhouse",
        "case_06_irregular_l_plot",
        "case_07_tight_urban",
        "case_08_multi_bedroom",
        "case_09_attached_suite",
        "case_10_separation_heavy",
        "case_11_adjacency_heavy",
        "case_12_preferred_relationships",
        "case_13_staircase_core",
        "case_14_orientation_east",
        "case_15_feasibility_edge",
        "case_16_infeasible_deficit",
    ]

    for cid in expected_ids:
        case = BenchmarkRegistry.get_case(cid)
        assert case is not None, f"Missing benchmark case: {cid}"
        assert case.brief.strip() != ""
        assert len(case.tags) > 0


def test_benchmark_tag_filtering():
    """Verify filtering benchmark cases by category tags."""
    single_floor_cases = BenchmarkRegistry.filter_by_tags([BenchmarkCategory.SINGLE_FLOOR])
    assert len(single_floor_cases) >= 8

    multi_floor_cases = BenchmarkRegistry.filter_by_tags([BenchmarkCategory.MULTI_FLOOR])
    assert len(multi_floor_cases) >= 3
    for c in multi_floor_cases:
        assert c.has_tag(BenchmarkCategory.MULTI_FLOOR)

    infeasible_cases = BenchmarkRegistry.filter_by_tags([BenchmarkCategory.INFEASIBLE])
    assert len(infeasible_cases) >= 1
    assert infeasible_cases[0].case_id == "case_16_infeasible_deficit"


def test_benchmark_id_filtering():
    """Verify filtering benchmark cases by explicit IDs."""
    selected = BenchmarkRegistry.filter_by_ids(["case_01_small_single_floor", "case_04_two_floor_family"])
    assert len(selected) == 2
    assert selected[0].case_id == "case_01_small_single_floor"
    assert selected[1].case_id == "case_04_two_floor_family"
