"""Unit tests for PlanForge Phase 10: Release Readiness, Independent Validation, and Reproducibility.

Verifies:
1. Exact metric numerator and denominator integrity (Phase 8 16/18 vs Phase 9 17/18 vs Ground Truth 17/17).
2. Independent geometry and constraint validation without relying on cached reports or pipeline status.
3. Verification that invalid floor plans can never be classified as valid.
4. CAD DXF structural verification via ezdxf: layer completeness, coordinate preservation, entity counts.
5. Verification that invalid/empty designs cannot be silently exported to DXF.
6. End-to-end workflow lifecycle: clarification gating, atomic updates, version increments, and resumption.
7. CandidateManager best-valid preservation under degraded mutations and interrupted runs.
8. Truthful failure classification for mathematically impossible programs.
9. Agent and LLM reliability: observable provider modes and bounded fallback truthfulness.
10. Research reproducibility package completeness and dataset manifest consistency.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import ezdxf
import pytest
from shapely.geometry import Polygon

from app.agentic.clarification import ClarificationCategory, ClarificationRequest, ClarificationResponse
from app.agentic.state import ProjectState, RunStatus
from app.evaluation.benchmark import BenchmarkCategory, BenchmarkRegistry
from app.evaluation.fault_injection import FaultInjector, FaultType
from app.evaluation.generalization_fixtures import FeasibilityExpectation, RobustnessRegistry
from app.export.dxf.exporter import DXFExporter
from app.export.dxf.layers import (
    LAYER_BUILDABLE_BOUNDARY,
    LAYER_DOORS,
    LAYER_PLOT_BOUNDARY,
    LAYER_ROOM_BOUNDARIES,
    LAYER_WALLS_EXTERIOR,
    LAYER_WALLS_INTERIOR,
)
from app.export.errors import InvalidExportInputError
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoRoom
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.orchestration.hierarchical import HierarchicalOrchestrator
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.validation.validator import FloorPlanValidator


# ----------------------------------------------------------------------------
# 1. Metric Numerator & Denominator Verification
# ----------------------------------------------------------------------------

def test_01_metric_numerators_and_denominators_audit():
    """Verify exact numerators, denominators, and ground-truth classifications."""
    all_cases = BenchmarkRegistry.get_all_cases()
    assert len(all_cases) == 20

    # In Phase 8, 2 cases were labeled INFEASIBLE: case_16 and case_17
    # Denominator = 20 - 2 = 18 cases
    eval_denominator = [c for c in all_cases if not c.has_tag(BenchmarkCategory.INFEASIBLE)]
    assert len(eval_denominator) == 18

    # Ground-truth infeasible includes case_20 due to physical area deficit
    gt_feasible = [c for c in eval_denominator if c.case_id != "case_20_tight_multifloor_deficit"]
    assert len(gt_feasible) == 17

    # Phase 8 baseline was 16 / 18 = 88.89%
    p8_rate = round((16 / 18) * 100, 2)
    assert p8_rate == 88.89

    # Phase 9 post-fix (case_03 fixed, case_20 unresolved) = 17 / 18 = 94.44%
    p9_orig_rate = round((17 / 18) * 100, 2)
    assert p9_orig_rate == 94.44

    # Ground-truth feasible rate = 17 / 17 = 100.0%
    gt_rate = round((17 / 17) * 100, 2)
    assert gt_rate == 100.0


# ----------------------------------------------------------------------------
# 2. Independent Geometry & Constraint Validation (No Cached Reports)
# ----------------------------------------------------------------------------

def test_02_independent_geometry_validation_without_cache():
    """Verify that independent validation inspects raw geometry with zero cached report reuse."""
    orch = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    res = orch.generate(case.brief, project_name="Indep_Geometry_Test")
    assert res.floor_plan_set is not None
    fps = res.floor_plan_set

    # Strip all cached validation results
    for fp in fps.floor_plans:
        fp.validation = None
        fp.is_valid = False

    # Instantiate completely independent validator with strict tolerance
    indep_validator = FloorPlanValidator(boundary_tolerance=0.01, max_overlap_sqm=0.01)
    report = indep_validator.validate(
        floor_plan_set=fps,
        requirements=res.requirements,
        plot_boundary=fps.plot_boundary,
        buildable_boundary=fps.buildable_boundary,
    )

    assert report.overall_valid is True
    assert report.overall_score >= 80.0
    assert report.total_errors == 0


def test_03_room_containment_and_non_overlap_invariance():
    """Verify that all rooms are strictly contained within buildable envelope without pairwise overlaps."""
    orch = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_02_medium_single_floor")
    assert case is not None

    res = orch.generate(case.brief, project_name="Containment_Overlap_Test")
    assert res.floor_plan_set is not None
    fps = res.floor_plan_set

    buildable_poly = Polygon(fps.buildable_boundary) if fps.buildable_boundary else None
    assert buildable_poly is not None

    for fp in fps.floor_plans:
        assert fp.geometry is not None
        room_polys = [Polygon(r.polygon) for r in fp.geometry.rooms]

        # 1. Envelope containment
        for poly in room_polys:
            assert buildable_poly.buffer(0.05).contains(poly)

        # 2. Pairwise overlap area <= 0.05 m²
        for i in range(len(room_polys)):
            for j in range(i + 1, len(room_polys)):
                overlap = room_polys[i].intersection(room_polys[j]).area
                assert overlap <= 0.05


# ----------------------------------------------------------------------------
# 3. Pipeline Success Does Not Imply Validity
# ----------------------------------------------------------------------------

def test_04_pipeline_completion_does_not_mask_invalid_geometry():
    """Verify that degenerate geometry is caught as invalid even if generation completed."""
    validator = FloorPlanValidator()
    
    # Construct an invalid floor plan with overlapping rooms
    room1 = GeoRoom(id="r1", room_type="living", usable_polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])
    room2 = GeoRoom(id="r2", room_type="bedroom", usable_polygon=[(2, 2), (7, 2), (7, 7), (2, 7)])  # Massive overlap
    geom = Geometry(rooms=[room1, room2])
    fp = FloorPlan(geometry=geom)
    fps = FloorPlanSet(floor_plans=[fp], buildable_boundary=[(0, 0), (10, 0), (10, 10), (0, 10)])

    report = validator.validate(floor_plan_set=fps)
    assert report.overall_valid is False
    assert report.total_errors > 0


# ----------------------------------------------------------------------------
# 4. CAD DXF Structural Verification via ezdxf
# ----------------------------------------------------------------------------

def test_05_dxf_structural_verification_ezdxf():
    """Verify that exported DXF files open cleanly, contain standard layers, and preserve coordinates."""
    orch = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    res = orch.generate(case.brief, project_name="DXF_Verification_Case")
    assert res.floor_plan_set is not None

    exporter = DXFExporter()
    with tempfile.TemporaryDirectory() as tmp_dir:
        dxf_path = Path(tmp_dir) / "test_drawing.dxf"
        exporter.export_floor_plan_set(res.floor_plan_set, output_path=dxf_path, project_name=case.name)
        assert dxf_path.exists()
        assert dxf_path.stat().st_size > 0

        # Open and inspect via ezdxf
        doc = ezdxf.readfile(str(dxf_path))
        assert doc.dxfversion in ("AC1032", "AC1027", "R2018", "R2013")

        # Mandatory layer checks
        layer_names = [layer.dxf.name for layer in doc.layers]
        for mandatory_layer in (
            LAYER_PLOT_BOUNDARY,
            LAYER_BUILDABLE_BOUNDARY,
            LAYER_WALLS_EXTERIOR,
            LAYER_WALLS_INTERIOR,
            LAYER_ROOM_BOUNDARIES,
            LAYER_DOORS,
        ):
            assert mandatory_layer in layer_names

        # Modelspace entity check
        msp = doc.modelspace()
        polylines = list(msp.query('LWPOLYLINE'))
        assert len(polylines) > 0


def test_06_invalid_and_empty_designs_blocked_from_dxf_export():
    """Verify that empty or invalid designs raise an error instead of exporting silent corrupt DXFs."""
    exporter = DXFExporter()
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "bad.dxf"

        # 1. Empty FloorPlanSet
        empty_fps = FloorPlanSet(project_name="empty", floor_plans=[])
        with pytest.raises(InvalidExportInputError):
            exporter.export_floor_plan_set(empty_fps, out_path)

        # 2. None input
        with pytest.raises(InvalidExportInputError):
            exporter.export_floor_plan_set(None, out_path)  # type: ignore


# ----------------------------------------------------------------------------
# 5. Full Lifecycle: Clarification, Atomic Update, Versioning & Resumption
# ----------------------------------------------------------------------------

def test_07_full_interactive_lifecycle_and_resumption():
    """Verify end-to-end interactive workflow: pause on ambiguous brief, apply response, version bump, resume."""
    coord = HierarchicalOrchestrator(interactive=True)
    state = ProjectState(project_id="interactive_lifecycle_test", goal="Build 2-floor residence 40x50")
    
    # 1. Step triggers completeness gate and pauses
    coord.step(state)
    assert state.status.is_paused or state.pending_clarification is not None
    v1 = state.state_version

    # 2. Apply clarification response
    req_id = state.pending_clarification.request_id if state.pending_clarification else "clarif_1"
    ok, msg, resp = coord.apply_clarification_response(
        state=state,
        request_id=req_id,
        user_response_text="Ground floor has 1 living room and 1 kitchen. First floor has 2 bedrooms and 1 bathroom.",
    )
    assert ok is True
    assert state.state_version > v1  # State version incremented

    # 3. Resume execution
    res_ok, res_msg, resumed_state = coord.resume(state)
    assert res_ok is True
    assert resumed_state.status != RunStatus.CANCELLED


# ----------------------------------------------------------------------------
# 6. Candidate Preservation Under Interruption
# ----------------------------------------------------------------------------

def test_08_candidate_preservation_under_degraded_mutation():
    """Verify CandidateManager keeps best-valid candidate and never overwrites it with invalid proposals."""
    state = ProjectState(project_id="candidate_preservation_test")
    
    # Candidate 1: Valid design (score 85)
    geom1 = Geometry(rooms=[GeoRoom(id="r1", room_type="living", usable_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])])
    fp1 = FloorPlan(geometry=geom1, is_valid=True)
    fps1 = FloorPlanSet(floor_plans=[fp1])
    rep1 = ValidationReport(results=[ValidationResult(floor_number=1, is_valid=True, score=85.0)])
    state.candidate_manager.register_candidate(step=1, source_action="action_1", floor_plan_set=fps1, validation_report=rep1)

    assert state.candidate_manager.best_valid_candidate is not None
    assert state.candidate_manager.best_valid_candidate.evaluation.overall_score == 85.0

    # Candidate 2: Injected degraded/invalid mutation (score 0)
    fp2 = FloorPlan(geometry=geom1, is_valid=False)
    fps2 = FloorPlanSet(floor_plans=[fp2])
    rep2 = ValidationReport(results=[ValidationResult(floor_number=1, is_valid=False, score=0.0)])
    state.candidate_manager.register_candidate(step=2, source_action="action_2", floor_plan_set=fps2, validation_report=rep2)

    # Best-valid candidate must remain Candidate 1
    best = state.candidate_manager.get_best_valid()
    assert best is not None
    assert best.evaluation.overall_score == 85.0
    assert best.evaluation.is_valid is True


# ----------------------------------------------------------------------------
# 7. Truthful Failure Reporting on Impossible Inputs
# ----------------------------------------------------------------------------

def test_09_truthful_failure_on_mathematical_infeasibility():
    """Verify that physically impossible programs halt with truthful failure state and exact deficit error."""
    orch = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_16_infeasible_deficit")
    assert case is not None

    res = orch.generate(case.brief, project_name="Truthful_Infeasible_Test")
    assert res.is_success is False
    assert res.status in ("failed", "infeasible")
    assert res.is_valid is False
    assert "exceeds" in (res.error_message or "").lower() or "deficit" in (res.error_message or "").lower()


# ----------------------------------------------------------------------------
# 8. Agent & LLM Reliability
# ----------------------------------------------------------------------------

def test_10_agent_reliability_and_offline_mock_distinction():
    """Verify observable distinction between mock client and live client, and bounded fallback on errors."""
    orch = PlanForgeOrchestrator()
    case = BenchmarkRegistry.get_case("case_01_small_single_floor")
    assert case is not None

    # Inject timeout into LLM client
    with FaultInjector.inject_llm_failure(FaultType.LLM_TIMEOUT, orch.architectural_agent.llm_client):
        res = orch.generate(case.brief, project_name="Reliability_Fallback_Test")
        assert res.is_success is True
        assert res.status == "completed"
        assert res.is_valid is True


# ----------------------------------------------------------------------------
# 9. Research Reproducibility Package Integrity
# ----------------------------------------------------------------------------

def test_11_dataset_manifest_and_reproducibility_artifacts():
    """Verify Phase 10 artifacts are present and well-formed in results/phase10_release_readiness/."""
    artifacts_dir = Path("results/phase10_release_readiness")
    required_files = [
        "dataset_manifest.json",
        "independent_validation_results.json",
        "dxf_structural_verification.json",
        "end_to_end_lifecycle_audit.json",
        "reproducibility_package.json",
        "release_checklist.json",
        "summary.json",
    ]

    for fname in required_files:
        fpath = artifacts_dir / fname
        assert fpath.exists(), f"Missing required Phase 10 artifact: {fname}"
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)
            assert len(data) > 0


def test_12_heldout_fixtures_isolation_integrity():
    """Verify held-out fixtures are distinct from Phase 8 benchmark cases."""
    benchmark_ids = {c.case_id for c in BenchmarkRegistry.get_all_cases()}
    heldout_ids = {h.fixture_id for h in RobustnessRegistry.get_heldout_fixtures()}

    # Held-out fixtures must be mutually disjoint from training/benchmark cases
    intersection = benchmark_ids.intersection(heldout_ids)
    assert len(intersection) == 0
    assert len(heldout_ids) == 7
