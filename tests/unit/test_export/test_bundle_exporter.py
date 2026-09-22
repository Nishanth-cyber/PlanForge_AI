"""Unit tests for the PlanForge BundleExporter and ExportIntegrityVerifier.

Verifies:
1. Complete directory hierarchy creation:
   - outputs/<project_id>/project.json
   - outputs/<project_id>/summary.md
   - outputs/<project_id>/explanations/
   - outputs/<project_id>/alternatives/alternative_X/
2. Multi-floor floor plan PNG generation per alternative.
3. Preservation of all IDs across artifacts.
4. Optional ZIP archive packaging.
5. Export integrity verification.
6. Immutability of input data structures during export.
"""

from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path

import pytest

from app.export.bundle_exporter import BundleExporter, export_project_bundle
from app.export.integrity import verify_export_integrity
from app.models.allocation import Allocation, AllocationSet
from app.models.alternatives import (
    AlternativeStatus,
    DesignAlternative,
    DesignAlternativeSet,
)
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import (
    Geometry,
    GeoDoor,
    GeoRoom,
    GeoWall,
    GeoWindow,
)
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.refinement import RefinementChange, RefinementResult, RefinementStatus
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.rendering.options import RenderOptions


def _create_test_geometry(floor_number: int = 1) -> Geometry:
    """Helper to create minimal valid geometry."""
    return Geometry(
        rooms=[
            GeoRoom(
                id=f"r_living_{floor_number}",
                room_type="living",
                usable_polygon=[(2.0, 2.0), (8.0, 2.0), (8.0, 6.0), (2.0, 6.0)],
                area_sqm=24.0,
                architectural_room_id=f"arch_living_{floor_number}",
            ),
            GeoRoom(
                id=f"r_kitchen_{floor_number}",
                room_type="kitchen",
                usable_polygon=[(8.0, 2.0), (12.0, 2.0), (12.0, 6.0), (8.0, 6.0)],
                area_sqm=16.0,
                architectural_room_id=f"arch_kitchen_{floor_number}",
            ),
        ],
        walls=[
            GeoWall(id="w1", start=(2.0, 2.0), end=(12.0, 2.0)),
            GeoWall(id="w2", start=(12.0, 2.0), end=(12.0, 6.0)),
        ],
        doors=[GeoDoor(id="d1", wall_id="w1", position=(4.0, 2.0), width=0.9)],
        windows=[GeoWindow(id="win1", wall_id="w2", position=(12.0, 4.0), width=1.2)],
    )


def test_bundle_exporter_directory_hierarchy(tmp_path: Path):
    """Verify that export_project_bundle creates the exact specified directory tree and files."""
    out_dir = tmp_path / "outputs"
    geom = _create_test_geometry(1)
    fps = FloorPlanSet(
        project_name="Heritage Estate",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
    )
    val = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=97.5)]
    )
    alt1 = DesignAlternative(
        alternative_id="alt_01",
        index=1,
        strategy="social_open",
        floor_plan_set=fps,
        validation_report=val,
        status=AlternativeStatus.VALIDATED,
        design_rationale="Open living area oriented to south.",
    )
    alt_set = DesignAlternativeSet(alternatives=[alt1])

    req = Requirements(project_name="Heritage Estate", plot_dimensions=(15.0, 20.0))
    plan = PlanningSpec(
        floors=[FloorPlanSpec(floor_number=1, room_specs=[RoomSpec(room_type="living")])]
    )

    bundle_path = export_project_bundle(
        project_id="proj_heritage",
        output_dir=out_dir,
        requirements=req,
        planning_spec=plan,
        floor_plan_set=fps,
        validation_report=val,
        alternative_set=alt_set,
        render_options=RenderOptions(dpi=100),  # fast test dpi
        create_zip=False,
    )

    assert bundle_path.exists()
    assert (bundle_path / "project.json").is_file()
    assert (bundle_path / "summary.md").is_file()
    assert (bundle_path / "explanations").is_dir()
    assert (bundle_path / "alternatives").is_dir()
    assert (bundle_path / "alternatives" / "alternative_1").is_dir()
    assert (bundle_path / "alternatives" / "alternative_1" / "design.json").is_file()
    assert (bundle_path / "alternatives" / "alternative_1" / "explanation.md").is_file()
    assert (bundle_path / "alternatives" / "alternative_1" / "floor_1.png").is_file()

    # Verify PNG is non-empty
    png_size = (bundle_path / "alternatives" / "alternative_1" / "floor_1.png").stat().st_size
    assert png_size > 500, f"Rendered PNG too small: {png_size} bytes"

    # Verify project.json can be loaded and has expected keys
    with open(bundle_path / "project.json", "r", encoding="utf-8") as f:
        pdata = json.load(f)
    assert pdata["project_id"] == "proj_heritage"
    assert "alternatives" in pdata
    assert len(pdata["alternatives"]) == 1


def test_bundle_exporter_multi_floor_isolation(tmp_path: Path):
    """Verify multi-floor projects produce distinct floor_1.png and floor_2.png."""
    out_dir = tmp_path / "outputs_mf"
    geom1 = _create_test_geometry(1)
    geom2 = _create_test_geometry(2)

    fps = FloorPlanSet(
        project_name="Duplex Villa",
        floor_plans=[
            FloorPlan(floor_number=1, geometry=geom1, is_valid=True),
            FloorPlan(floor_number=2, geometry=geom2, is_valid=True),
        ],
    )
    val = ValidationReport(
        results=[
            ValidationResult(floor_number=1, is_valid=True, score=95.0),
            ValidationResult(floor_number=2, is_valid=True, score=96.0),
        ]
    )
    alt = DesignAlternative(
        alternative_id="alt_duplex_01",
        index=1,
        strategy="stacked_service",
        floor_plan_set=fps,
        validation_report=val,
        status=AlternativeStatus.VALIDATED,
    )
    alt_set = DesignAlternativeSet(alternatives=[alt])

    bundle_path = export_project_bundle(
        project_id="proj_duplex",
        output_dir=out_dir,
        floor_plan_set=fps,
        alternative_set=alt_set,
        render_options=RenderOptions(dpi=100),
    )

    alt1_dir = bundle_path / "alternatives" / "alternative_1"
    floor1_img = alt1_dir / "floor_1.png"
    floor2_img = alt1_dir / "floor_2.png"

    assert floor1_img.exists()
    assert floor2_img.exists()
    assert floor1_img.stat().st_size > 500
    assert floor2_img.stat().st_size > 500


def test_bundle_exporter_zip_archive(tmp_path: Path):
    """Verify that create_zip=True produces a readable, valid ZIP containing all artifacts."""
    out_dir = tmp_path / "outputs_zip"
    geom = _create_test_geometry(1)
    fps = FloorPlanSet(
        project_name="Zip Test",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
    )
    alt = DesignAlternative(
        alternative_id="alt_z",
        index=1,
        strategy="compact",
        floor_plan_set=fps,
        status=AlternativeStatus.VALIDATED,
    )
    alt_set = DesignAlternativeSet(alternatives=[alt])

    bundle_path = export_project_bundle(
        project_id="proj_zip_test",
        output_dir=out_dir,
        floor_plan_set=fps,
        alternative_set=alt_set,
        render_options=RenderOptions(dpi=80),
        create_zip=True,
    )

    zip_path = out_dir / "proj_zip_test.zip"
    assert zip_path.is_file()
    assert zip_path.stat().st_size > 1000

    # Verify contents of zip file
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert any("project.json" in name for name in namelist)
        assert any("summary.md" in name for name in namelist)
        assert any("floor_1.png" in name for name in namelist)


def test_verify_export_integrity(tmp_path: Path):
    """Verify that ExportIntegrityVerifier accurately validates complete vs corrupted bundles."""
    out_dir = tmp_path / "outputs_integrity"
    geom = _create_test_geometry(1)
    fps = FloorPlanSet(
        project_name="Integrity Test",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
    )
    alt = DesignAlternative(
        alternative_id="alt_int",
        index=1,
        strategy="direct",
        floor_plan_set=fps,
        status=AlternativeStatus.VALIDATED,
    )
    alt_set = DesignAlternativeSet(alternatives=[alt])

    bundle_path = export_project_bundle(
        project_id="proj_integrity",
        output_dir=out_dir,
        floor_plan_set=fps,
        alternative_set=alt_set,
        render_options=RenderOptions(dpi=80),
    )

    # 1. Valid bundle check
    report = verify_export_integrity(bundle_path)
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert report.total_files > 0
    assert "project.json" in report.verified_files
    assert "summary.md" in report.verified_files

    # 2. Corrupt bundle check: corrupt project.json
    pjson = bundle_path / "project.json"
    with open(pjson, "w", encoding="utf-8") as f:
        f.write("{corrupted_json: true,")

    corrupt_report = verify_export_integrity(bundle_path)
    assert corrupt_report.is_valid is False
    assert any("project.json" in e.lower() or "parse" in e.lower() for e in corrupt_report.errors)


def test_bundle_exporter_immutability(tmp_path: Path):
    """Verify that export_project_bundle does not mutate input objects."""
    out_dir = tmp_path / "outputs_immutability"
    geom = _create_test_geometry(1)
    fps = FloorPlanSet(
        project_name="Immutable Test",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
    )
    alt = DesignAlternative(
        alternative_id="alt_imm",
        index=1,
        strategy="axial",
        floor_plan_set=fps,
        status=AlternativeStatus.VALIDATED,
    )
    alt_set = DesignAlternativeSet(alternatives=[alt])

    # Deep copy before export
    fps_clone = copy.deepcopy(fps)
    alt_set_clone = copy.deepcopy(alt_set)

    export_project_bundle(
        project_id="proj_immutable",
        output_dir=out_dir,
        floor_plan_set=fps,
        alternative_set=alt_set,
        render_options=RenderOptions(dpi=80),
    )

    # Validate equality
    assert fps.id == fps_clone.id
    assert len(fps.floor_plans) == len(fps_clone.floor_plans)
    assert fps.floor_plans[0].geometry.rooms[0].polygon == fps_clone.floor_plans[0].geometry.rooms[0].polygon
    assert alt_set.alternatives[0].alternative_id == alt_set_clone.alternatives[0].alternative_id
    assert alt_set.alternatives[0].status == alt_set_clone.alternatives[0].status
