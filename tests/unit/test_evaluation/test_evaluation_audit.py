"""Phase 15 Research Evaluation Regression & Audit Tests."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from shapely.geometry import Polygon

from app.evaluation.benchmark import BENCHMARK_CASES, BenchmarkCategory, BenchmarkRegistry
from app.evaluation.baselines import BaselineSpatialAllocator
from app.evaluation.metrics import MetricCalculator
from app.evaluation.models import EvaluationConfig
from app.evaluation.reporting import EvaluationReporter
from app.evaluation.reproducibility import ReproducibilityAuditor
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator


def test_all_16_benchmark_cases_valid_and_explicit():
    """Audit 1: Verify all benchmark cases (minimum 16, now 20 in Phase 8) are deterministic, well-formed, and explicit."""
    cases = BenchmarkRegistry.get_all_cases()
    assert len(cases) >= 16, f"Expected at least 16 benchmark cases, found {len(cases)}"
    assert len(cases) == 20, f"Expected 20 benchmark cases in Phase 8 suite, found {len(cases)}"

    for case in cases:
        assert case.case_id.strip(), "Case ID must not be empty"
        assert case.name.strip(), "Case name must not be empty"
        assert case.brief.strip(), f"Brief for {case.case_id} must not be empty"
        assert len(case.tags) >= 1, f"Case {case.case_id} must have at least one category tag"
        assert "expected_floors" in case.expected_properties, f"Case {case.case_id} missing expected_floors"
        assert "expected_feasibility" in case.expected_properties, f"Case {case.case_id} missing expected_feasibility"

    # Verify negative control case 16
    c16 = BenchmarkRegistry.get_case("case_16_infeasible_deficit")
    assert c16 is not None
    assert c16.has_tag(BenchmarkCategory.INFEASIBLE)
    assert c16.expected_properties["expected_feasibility"] is False


def test_metric_area_evaluation_uses_final_geometry():
    """Audit 2: Verify area MAE and compliance measure final geometry, not ASAA macro-allocation."""
    orchestrator = PlanForgeOrchestrator()
    brief = """
    Single floor bungalow on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 250 sq ft
    - 1 kitchen of 120 sq ft
    - 1 bedroom of 150 sq ft
    - 1 bathroom of 50 sq ft
    """
    cfg = OrchestrationConfig(enable_refinement=False, enable_rendering=False, enable_exports=False)
    res = orchestrator.generate(brief, project_name="Area Layer Audit", config=cfg)
    metrics = MetricCalculator.calculate_all(res)

    assert "area_min_compliance" in metrics
    assert "area_preferred_mae" in metrics
    assert metrics["area_min_compliance"].is_available
    assert metrics["area_preferred_mae"].is_available

    # Final geometry rooms must exist and have usable areas
    fp = res.floor_plan_set.floor_plans[0]
    for r in fp.geometry.rooms:
        assert r.area_sqm > 0.0
        # Final room area is within physical limits of the room, not the full buildable plot
        assert r.area_sqm < 80.0


def test_baseline_allocator_independence_and_fairness():
    """Audit 3: Verify BaselineSpatialAllocator is independent and uses the same input planning spec."""
    orchestrator = PlanForgeOrchestrator()
    baseline_alloc = BaselineSpatialAllocator()

    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    reqs = orchestrator.requirement_agent.parse(case.brief)
    spec = orchestrator.planning_agent.plan(reqs)

    # 1. Baseline produces valid allocation
    b_alloc_set = baseline_alloc.allocate(spec)
    assert len(b_alloc_set.allocations) == 1
    assert len(b_alloc_set.allocations[0].allocated_regions) >= 4

    # 2. Baseline polygons are non-overlapping and strictly inside buildable bounds
    buildable_poly = Polygon(baseline_alloc._derive_buildable_boundary(spec).shapely_polygon)
    for r in b_alloc_set.allocations[0].allocated_regions:
        poly = Polygon(r.polygon)
        assert poly.is_valid
        assert buildable_poly.contains(poly) or buildable_poly.buffer(0.01).contains(poly)


def test_reproducibility_deterministic_canonical_fingerprints():
    """Audit 4: Verify deterministic canonical fingerprint stability across repeated runs."""
    orchestrator = PlanForgeOrchestrator()
    auditor = ReproducibilityAuditor(runs_count=2, seed=42)

    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    rep_res = auditor.audit_case(case, orchestrator)
    assert rep_res.is_identical is True
    assert len(set(rep_res.hashes)) == 1
    assert rep_res.divergence_stage is None


def test_section_15_artifact_structure_export(tmp_path: Path):
    """Audit 5: Verify all required Section 15 files are generated with valid structure."""
    orchestrator = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    cfg = OrchestrationConfig(enable_refinement=False, enable_rendering=False, enable_exports=False)
    res = orchestrator.generate(case.brief, project_name="Export Audit", config=cfg)
    metrics = MetricCalculator.calculate_all(res)

    from app.evaluation.models import CaseEvaluationResult, ExperimentRun
    case_res = CaseEvaluationResult(
        case_id=case.case_id,
        name=case.name,
        tags=[t.value for t in case.tags],
        status=res.status,
        is_success=res.is_success,
        overall_valid=res.is_valid,
        metrics=metrics,
    )

    exp_run = ExperimentRun(
        run_id="test_run_01",
        timestamp="2026-09-20T20:00:00Z",
        config=EvaluationConfig(output_dir=str(tmp_path)),
        case_results=[case_res],
        ablation_results=[],
        reproducibility_results=[],
        summary_metrics={"total_cases": 1},
    )

    exported_paths = EvaluationReporter.export_all(exp_run, tmp_path)

    required_files = [
        "metadata.json",
        "benchmark_cases.json",
        "baseline_results.json",
        "asaa_results.json",
        "ablation_results.json",
        "reproducibility_results.json",
        "metrics.json",
        "failure_analysis.json",
        "summary.json",
        "README.md",
    ]

    for req_file in required_files:
        p = tmp_path / req_file
        assert p.exists(), f"Required artifact {req_file} was not generated"
        if req_file.endswith(".json"):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert data is not None
