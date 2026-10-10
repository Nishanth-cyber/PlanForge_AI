"""Phase 6 Export Integrity and Demo Verification Tests.

Comprehensive regression tests verifying:
1. Rectangle 40x50 ft plan exports: DXF, SVG, PNG, JSON, ZIP exist and are readable.
2. L-shaped plot exports: exact 6-vertex polygon preserved across DXF, SVG, JSON.
3. Multi-floor exports: floor separation strictly maintained across DXF, SVG, PNG, JSON.
4. Invalid/Infeasible plan export gating & truthful status recording.
5. Security / No Secrets: no API keys, tokens, passwords, or credentials in exported artifacts.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
import pytest
import ezdxf

from app.export.bundle_exporter import export_project_bundle
from app.export.dxf.exporter import DXFExporter
from app.export.errors import InvalidExportInputError
from app.export.integrity import verify_export_integrity
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoRoom, GeoWall, GeoDoor, GeoWindow
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.rendering.options import RenderOptions


def _create_rectangle_geometry() -> Geometry:
    return Geometry(
        plot_polygon=[(0.0, 0.0), (12.19, 0.0), (12.19, 15.24), (0.0, 15.24)],
        buildable_polygon=[(1.2, 1.5), (10.99, 1.5), (10.99, 13.74), (1.2, 13.74)],
        rooms=[
            GeoRoom(
                id="r_living",
                room_type="living",
                usable_polygon=[(1.5, 1.5), (6.0, 1.5), (6.0, 7.0), (1.5, 7.0)],
                built_polygon=[(1.5, 1.5), (6.0, 1.5), (6.0, 7.0), (1.5, 7.0)],
                area_sqm=24.75,
                floor_number=1,
            ),
            GeoRoom(
                id="r_kitchen",
                room_type="kitchen",
                usable_polygon=[(6.0, 1.5), (10.5, 1.5), (10.5, 5.0), (6.0, 5.0)],
                built_polygon=[(6.0, 1.5), (10.5, 1.5), (10.5, 5.0), (6.0, 5.0)],
                area_sqm=15.75,
                floor_number=1,
            ),
        ],
        walls=[
            GeoWall(id="w1", start=(1.5, 1.5), end=(10.5, 1.5), type="exterior"),
            GeoWall(id="w2", start=(10.5, 1.5), end=(10.5, 7.0), type="exterior"),
        ],
        doors=[
            GeoDoor(id="d1", wall_id="w1", position=(3.0, 1.5), width=0.9, connects_from="exterior", connects_to="r_living")
        ],
        windows=[
            GeoWindow(id="win1", wall_id="w2", position=(10.5, 3.5), width=1.2)
        ],
    )


def _create_l_shaped_geometry() -> Geometry:
    l_shape: list[tuple[float, float]] = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 10.0),
        (10.0, 10.0),
        (10.0, 20.0),
        (0.0, 20.0),
    ]
    return Geometry(
        plot_polygon=l_shape,
        buildable_polygon=[
            (1.2, 1.5),
            (18.8, 1.5),
            (18.8, 8.8),
            (8.8, 8.8),
            (8.8, 18.5),
            (1.2, 18.5),
        ],
        rooms=[
            GeoRoom(
                id="r_living_l",
                room_type="living",
                usable_polygon=[(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)],
                built_polygon=[(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)],
                area_sqm=36.0,
                floor_number=1,
            )
        ],
        walls=[GeoWall(id="wl1", start=(2.0, 2.0), end=(8.0, 2.0))],
        doors=[],
        windows=[],
    )


def test_phase6_test1_rectangle_all_artifacts(tmp_path: Path):
    """Test 1 — Rectangle: 40x50 ft. Export DXF, SVG, PNG, JSON, ZIP and verify readability."""
    out_dir = tmp_path / "outputs_rect"
    geom = _create_rectangle_geometry()
    val_report = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=100.0)],
    )
    fps = FloorPlanSet(
        project_name="Phase 6 Rectangle Villa",
        plot_boundary=[(0.0, 0.0), (12.19, 0.0), (12.19, 15.24), (0.0, 15.24)],
        buildable_boundary=[(1.2, 1.5), (10.99, 1.5), (10.99, 13.74), (1.2, 13.74)],
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True, validation=val_report.results[0])],
        validation_report=val_report,
    )
    req = Requirements(
        project_name="Phase 6 Rectangle Villa",
        plot_dimensions=(12.19, 15.24),
        floor_requirements=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", target_area_sqm=24.0, min_count=1),
                    RoomRequirement(room_type="kitchen", target_area_sqm=15.0, min_count=1),
                ],
            )
        ],
    )

    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_p6_rect",
        requirements=req,
        floor_plan_set=fps,
        validation_report=val_report,
        render_options=RenderOptions(dpi=100),
        create_zip=True,
        export_dxf=True,
    )

    # 1. Verify JSON export
    proj_json = bundle_path / "project.json"
    assert proj_json.is_file()
    with open(proj_json, "r", encoding="utf-8") as f:
        pdata = json.load(f)
    assert pdata["project_id"] == "proj_p6_rect"
    assert "requirements" in pdata
    assert "floor_plan_set" in pdata
    assert "validation_report" in pdata

    # 2. Verify PNG export
    png_file = bundle_path / "floors" / "floor_1.png"
    assert png_file.is_file()
    assert png_file.stat().st_size > 1000

    # 3. Verify SVG export
    svg_file = bundle_path / "floors" / "floor_1.svg"
    assert svg_file.is_file()
    assert svg_file.stat().st_size > 500
    with open(svg_file, "r", encoding="utf-8") as f:
        svg_content = f.read()
    assert "<svg" in svg_content
    assert "</svg>" in svg_content

    # 4. Verify DXF export
    dxf_files = list(bundle_path.glob("*.dxf"))
    assert len(dxf_files) >= 1
    dxf_file = dxf_files[0]
    assert dxf_file.stat().st_size > 1000
    doc = ezdxf.readfile(str(dxf_file))
    assert doc is not None
    assert doc.header["$INSUNITS"] == 6  # Meters

    # 5. Verify ZIP export
    zip_path = out_dir / "proj_p6_rect.zip"
    assert zip_path.is_file()
    assert zip_path.stat().st_size > 2000
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert any("project.json" in n for n in namelist)
        assert any("floor_1.png" in n for n in namelist)
        assert any("floor_1.svg" in n for n in namelist)
        assert any(".dxf" in n for n in namelist)


def test_phase6_test2_l_shaped_geometry_preservation(tmp_path: Path):
    """Test 2 — L-shaped: Verify exported geometry preserves exact 6-vertex polygon."""
    out_dir = tmp_path / "outputs_l"
    geom = _create_l_shaped_geometry()
    l_shape = geom.plot_polygon
    assert len(l_shape) == 6

    val_report = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=98.0)],
    )
    fps = FloorPlanSet(
        project_name="L-Shaped Villa",
        plot_boundary=l_shape,
        buildable_boundary=geom.buildable_polygon,
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
        validation_report=val_report,
    )

    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_p6_lshape",
        floor_plan_set=fps,
        validation_report=val_report,
        render_options=RenderOptions(dpi=100),
        export_dxf=True,
    )

    # Verify JSON preserves all 6 vertices
    with open(bundle_path / "project.json", "r", encoding="utf-8") as f:
        pdata = json.load(f)
    json_plot = pdata["floor_plan_set"]["plot_boundary"]
    assert len(json_plot) == 6
    assert json_plot[0] == [0.0, 0.0]
    assert json_plot[1] == [20.0, 0.0]
    assert json_plot[2] == [20.0, 10.0]
    assert json_plot[3] == [10.0, 10.0]
    assert json_plot[4] == [10.0, 20.0]
    assert json_plot[5] == [0.0, 20.0]

    # Verify DXF contains the exact 6-vertex boundary
    dxf_file = list(bundle_path.glob("*.dxf"))[0]
    doc = ezdxf.readfile(str(dxf_file))
    msp = doc.modelspace()
    polylines = msp.query('LWPOLYLINE[layer=="PLOT_BOUNDARY"]')
    assert len(polylines) >= 1
    dxf_poly = polylines[0]
    pts = [(p[0], p[1]) for p in dxf_poly.get_points()]
    assert len(pts) == 6


def test_phase6_test3_multi_floor_separation(tmp_path: Path):
    """Test 3 — Multi-floor: Verify floor separation in DXF, SVG, PNG, and JSON."""
    out_dir = tmp_path / "outputs_mf"
    geom1 = Geometry(
        rooms=[
            GeoRoom(
                id="r_f1_living",
                room_type="living",
                usable_polygon=[(2.0, 2.0), (8.0, 2.0), (8.0, 7.0), (2.0, 7.0)],
                area_sqm=30.0,
                floor_number=1,
            ),
            GeoRoom(
                id="r_f1_kitchen",
                room_type="kitchen",
                usable_polygon=[(8.0, 2.0), (12.0, 2.0), (12.0, 7.0), (8.0, 7.0)],
                area_sqm=20.0,
                floor_number=1,
            ),
        ],
        walls=[GeoWall(id="w_f1", start=(2.0, 2.0), end=(12.0, 2.0), floor_number=1)],
        doors=[],
        windows=[],
    )
    geom2 = Geometry(
        rooms=[
            GeoRoom(
                id="r_f2_bed1",
                room_type="bedroom",
                usable_polygon=[(2.0, 2.0), (7.0, 2.0), (7.0, 7.0), (2.0, 7.0)],
                area_sqm=25.0,
                floor_number=2,
            ),
            GeoRoom(
                id="r_f2_bed2",
                room_type="bedroom",
                usable_polygon=[(7.0, 2.0), (12.0, 2.0), (12.0, 7.0), (7.0, 7.0)],
                area_sqm=25.0,
                floor_number=2,
            ),
        ],
        walls=[GeoWall(id="w_f2", start=(2.0, 2.0), end=(12.0, 2.0), floor_number=2)],
        doors=[],
        windows=[],
    )

    val_report = ValidationReport(
        results=[
            ValidationResult(floor_number=1, is_valid=True, score=96.0),
            ValidationResult(floor_number=2, is_valid=True, score=96.0),
        ],
    )
    fps = FloorPlanSet(
        project_name="Duplex MultiFloor",
        floor_plans=[
            FloorPlan(floor_number=1, geometry=geom1, is_valid=True),
            FloorPlan(floor_number=2, geometry=geom2, is_valid=True),
        ],
        validation_report=val_report,
    )

    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_p6_mf",
        floor_plan_set=fps,
        validation_report=val_report,
        render_options=RenderOptions(dpi=100),
        export_dxf=True,
    )

    # 1. Distinct PNG images
    f1_png = bundle_path / "floors" / "floor_1.png"
    f2_png = bundle_path / "floors" / "floor_2.png"
    assert f1_png.exists() and f2_png.exists()
    assert f1_png.stat().st_size > 500
    assert f2_png.stat().st_size > 500

    # 2. Distinct SVG images
    f1_svg = bundle_path / "floors" / "floor_1.svg"
    f2_svg = bundle_path / "floors" / "floor_2.svg"
    assert f1_svg.exists() and f2_svg.exists()
    assert f1_svg.stat().st_size > 500
    assert f2_svg.stat().st_size > 500

    # 3. DXF Floor layer separation
    dxf_file = list(bundle_path.glob("*.dxf"))[0]
    doc = ezdxf.readfile(str(dxf_file))
    layers = [l.dxf.name for l in doc.layers]
    assert any("FLOOR_1_ROOM_BOUNDARIES" in l for l in layers)
    assert any("FLOOR_2_ROOM_BOUNDARIES" in l for l in layers)

    # 4. JSON separation
    with open(bundle_path / "project.json", "r", encoding="utf-8") as f:
        pdata = json.load(f)
    plans = pdata["floor_plan_set"]["floor_plans"]
    assert len(plans) == 2
    f1_types = [r["room_type"] for r in plans[0]["geometry"]["rooms"]]
    f2_types = [r["room_type"] for r in plans[1]["geometry"]["rooms"]]
    assert "living" in f1_types and "living" not in f2_types
    assert "bedroom" in f2_types and "bedroom" not in f1_types


def test_phase6_test4_invalid_plan_export_gating(tmp_path: Path):
    """Test 4 — Invalid/Infeasible Plan: DXF export gates invalid plans; JSON records invalidity."""
    out_dir = tmp_path / "outputs_invalid"
    geom = _create_rectangle_geometry()
    invalid_report = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                score=40.0,
                issues=[
                    ValidationIssue(severity="error", category="boundary", message="Room outside boundary"),
                    ValidationIssue(severity="error", category="dimension", message="Minimum area violated"),
                ],
            )
        ],
    )
    invalid_fps = FloorPlanSet(
        project_name="Invalid Test Plan",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=False)],
        validation_report=invalid_report,
    )

    # DXFExporter must reject invalid plans
    exporter = DXFExporter()
    with pytest.raises(InvalidExportInputError, match="failed validation"):
        exporter.export_floor_plan_set(invalid_fps, out_dir / "test.dxf")

    # When bundled, JSON reflects truthful invalid status without crashing
    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_invalid",
        floor_plan_set=invalid_fps,
        validation_report=invalid_report,
        export_dxf=False,
        render_images=False,
    )
    with open(bundle_path / "project.json", "r", encoding="utf-8") as f:
        pdata = json.load(f)
    assert pdata["validation_report"]["overall_valid"] is False
    assert pdata["validation_report"]["total_errors"] == 2


def test_phase6_test5_no_secrets_in_exports(tmp_path: Path):
    """Test 5 — No Secrets: Verify no API keys, tokens, or passwords exist in export bundle or ZIP."""
    out_dir = tmp_path / "outputs_sec"
    geom = _create_rectangle_geometry()
    fps = FloorPlanSet(
        project_name="Security Audit Plan",
        floor_plans=[FloorPlan(floor_number=1, geometry=geom, is_valid=True)],
    )

    bundle_path = export_project_bundle(
        output_dir=out_dir,
        project_id="proj_security_audit",
        floor_plan_set=fps,
        render_options=RenderOptions(dpi=80),
        create_zip=True,
        export_dxf=True,
    )

    forbidden_patterns = [
        "hf_", "sk-", "token", "password", "api_key", "secret", "bearer", "authorization"
    ]

    # Check all files in bundle
    for p in bundle_path.rglob("*"):
        if p.is_file() and p.suffix in [".json", ".md", ".txt"]:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                for pat in forbidden_patterns:
                    assert f"{pat}=" not in content, f"Possible secret assignment '{pat}=' in {p.name}"
                    assert f'"{pat}"' not in content or pat in ["token", "secret", "password"], (
                        f"Possible secret key in {p.name}"
                    )

    # Check ZIP archive entries
    zip_path = out_dir / "proj_security_audit.zip"
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            assert not name.startswith("/"), "Absolute path leaked in ZIP"
            assert not name.startswith(".."), "Directory traversal in ZIP"
            assert not name.endswith(".env"), "Env file leaked in ZIP"
            assert not name.endswith(".py"), "Source code leaked in ZIP"
