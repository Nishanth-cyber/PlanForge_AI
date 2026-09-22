"""Unit tests for human-readable Markdown report generation and neutral presentation."""

import re
from pathlib import Path

from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.models.planning import PlanningSpec, FloorPlanSpec, RoomSpec
from app.models.allocation import AllocationSet, Allocation, AllocatedRegion
from app.models.floor_plan import FloorPlanSet, FloorPlan
from app.models.geometry import Geometry, GeoRoom, GeoWall, GeoDoor
from app.models.validation import ValidationReport, ValidationResult, ValidationIssue
from app.models.refinement import RefinementResult, RefinementChange, RefinementStatus
from app.models.alternatives import DesignAlternative, DesignAlternativeSet, AlternativeStatus
from app.explainability.models import DecisionTrace
from app.export.report_exporter import (
    generate_project_markdown_report,
    generate_alternative_markdown_report,
    save_markdown,
)


def test_generate_project_markdown_report(tmp_path: Path):
    """Verify that generate_project_markdown_report produces a complete, structured report."""
    req = Requirements(
        project_name="Villa Grand",
        plot_dimensions=(20.0, 25.0),
        plot_area_sqm=500.0,
        orientation="north",
        setbacks={"front": 3.0, "rear": 2.0, "side": 1.5},
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="living", target_area_sqm=35.0)],
            )
        ],
    )
    plan = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[RoomSpec(room_type="living", target_area_sqm=35.0, room_category="social")],
            )
        ]
    )
    alloc = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                total_area_sqm=350.0,
                circulation_area_sqm=40.0,
                allocated_regions=[AllocatedRegion(room_type="living", area_sqm=36.0)],
            )
        ]
    )
    geom = Geometry(
        floor_number=1,
        rooms=[
            GeoRoom(
                id="r1",
                room_type="living",
                area_sqm=35.5,
                walls=["w1", "w2"],
                doors=["d1"],
                windows=["win1"],
                architectural_room_id="arch_living_1",
            )
        ],
        walls=[GeoWall(id="w1"), GeoWall(id="w2")],
        doors=[GeoDoor(id="d1")],
    )
    fps = FloorPlanSet(
        project_name="Villa Grand",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
    )
    val = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=98.0)]
    )

    alt1 = DesignAlternative(
        alternative_id="alt_1",
        index=1,
        strategy="social_centric",
        status=AlternativeStatus.VALIDATED,
        characteristics=["direct social flow"],
        diversity_scores={"alt_2": 0.45},
    )
    alt2 = DesignAlternative(
        alternative_id="alt_2",
        index=2,
        strategy="corridor_centric",
        status=AlternativeStatus.VALIDATED,
        characteristics=["central corridor"],
        diversity_scores={"alt_1": 0.45},
    )
    alt_set = DesignAlternativeSet(
        alternatives=[alt1, alt2],
        requested_count=2,
        candidates_generated=3,
        strategies_attempted=["social_centric", "corridor_centric"],
    )

    trace = DecisionTrace(project_name="Villa Grand")

    report = generate_project_markdown_report(
        project_id="proj_villa",
        requirements=req,
        planning_spec=plan,
        allocation_set=alloc,
        floor_plan_set=fps,
        validation_report=val,
        alternative_set=alt_set,
        decision_trace=trace,
    )

    assert "# PlanForge AI — Floor Plan Generation Report: Villa Grand" in report
    assert "20.00m × 25.00m" in report
    assert "Orientation:** north" in report
    assert "VALID" in report
    assert "98.0 / 100.0" in report
    assert "| Floor 1 | Living | 35.50 | 2 | 1 | 1 | `arch_living_1` |" in report
    assert "### Alternative 1: Strategy `social_centric`" in report
    assert "### Alternative 2: Strategy `corridor_centric`" in report
    assert "Pairwise Structural Diversity Distances:" in report

    # Save to disk
    out_file = tmp_path / "report.md"
    saved = save_markdown(report, out_file)
    assert saved.exists()
    assert saved.stat().st_size > 500


def test_neutral_presentation_no_best_design():
    """Verify that reports never state or imply a 'best design', 'winner', or 'optimal alternative'."""
    alt1 = DesignAlternative(
        alternative_id="alt_1",
        index=1,
        strategy="social_centric",
        status=AlternativeStatus.VALIDATED,
    )
    alt2 = DesignAlternative(
        alternative_id="alt_2",
        index=2,
        strategy="corridor_centric",
        status=AlternativeStatus.VALIDATED,
    )
    alt_set = DesignAlternativeSet(alternatives=[alt1, alt2])

    report = generate_project_markdown_report(
        project_id="proj_neutral",
        alternative_set=alt_set,
    )

    report_lower = report.lower()
    assert "best design" not in report_lower
    assert "optimal design" not in report_lower
    assert "winner" not in report_lower
    assert "recommended alternative" not in report_lower
    assert "preferred alternative" not in report_lower


def test_validation_status_distinction():
    """Verify clean distinction between VALID, INVALID, and VALID WITH WARNINGS."""
    # 1. Fully Valid
    val_clean = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=100.0, issues=[])]
    )
    rep_clean = generate_project_markdown_report(project_id="p1", validation_report=val_clean)
    assert "**Validation Status:** **`VALID`**" in rep_clean

    # 2. Valid with Warnings
    val_warn = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=True,
                score=92.0,
                issues=[ValidationIssue(severity="warning", check="R_DIM", message="Target area slight deviation")],
            )
        ]
    )
    rep_warn = generate_project_markdown_report(project_id="p2", validation_report=val_warn)
    assert "**Validation Status:** **`VALID WITH WARNINGS`**" in rep_warn
    assert "Advisory Warnings:" in rep_warn

    # 3. Invalid
    val_err = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                score=45.0,
                issues=[ValidationIssue(severity="error", check="R_OVERLAP", message="Rooms overlap")],
            )
        ]
    )
    rep_err = generate_project_markdown_report(project_id="p3", validation_report=val_err)
    assert "**Validation Status:** **`INVALID`**" in rep_err
    assert "Critical Non-Compliance Errors:" in rep_err


def test_invalid_alternative_export_preservation():
    """Verify that an invalid or rejected alternative is explicitly marked as invalid."""
    alt_inv = DesignAlternative(
        alternative_id="alt_bad",
        index=3,
        strategy="compact_circulation",
        status=AlternativeStatus.INVALID,
        rejection_reason="door_clearance_failure",
        design_rationale="Failed swing clearance",
    )
    alt_set = DesignAlternativeSet(alternatives=[alt_inv])

    report = generate_project_markdown_report(project_id="p_inv", alternative_set=alt_set)
    assert "Status:** `invalid` (Valid: False)" in report


def test_alternative_markdown_report():
    """Verify single alternative markdown report generation."""
    alt = DesignAlternative(
        alternative_id="alt_detail",
        index=1,
        strategy="privacy_centric",
        status=AlternativeStatus.VALIDATED,
        characteristics=["clustered bedroom suites", "segregated service zone"],
        diversity_scores={"alt_2": 0.52},
    )
    md = generate_alternative_markdown_report(alt)
    assert "# Design Alternative 1 — Strategy: privacy_centric" in md
    assert "clustered bedroom suites" in md
    assert "0.520" in md
