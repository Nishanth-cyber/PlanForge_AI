"""Unit tests for the PlanForge DXF Exporter.

Verifies:
1. DXF export succeeds for a valid single-floor plan.
2. DXF file exists after export and is non-empty.
3. DXF can be parsed and read back by ezdxf.readfile().
4. Plot boundary is present on PLOT_BOUNDARY layer.
5. Room and wall geometry are present on designated layers.
6. Doors and windows are exported with geometric fidelity.
7. Door swing arcs are exported on DOOR_SWINGS layer.
8. Staircase geometry (footprint and treads) is exported.
9. Irregular plot vertices (e.g. L-shaped or trapezoidal) are strictly preserved.
10. Multi-floor geometry is exported correctly with floor-prefixed layers.
11. Invalid floor plans cannot be exported (raises InvalidExportInputError).
12. Exported coordinates match the source Geometry Engine coordinates within precision tolerance.
13. Deterministic DXF output across repeated exports.
"""

from __future__ import annotations
import math
from pathlib import Path
import pytest
import ezdxf

from app.export.dxf.exporter import (
    DXFExporter,
    export_floor_plan_set_to_dxf,
    get_dxf_filename,
    sanitize_project_name,
)
from app.export.dxf.layers import (
    LAYER_PLOT_BOUNDARY,
    LAYER_BUILDABLE_BOUNDARY,
    LAYER_WALLS_EXTERIOR,
    LAYER_WALLS_INTERIOR,
    LAYER_ROOM_BOUNDARIES,
    LAYER_DOORS,
    LAYER_DOOR_SWINGS,
    LAYER_WINDOWS,
    LAYER_STAIRCASES,
    LAYER_ROOM_LABELS,
    LAYER_DIMENSIONS,
)
from app.export.errors import InvalidExportInputError
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import (
    Geometry,
    GeoDoor,
    GeoRoom,
    GeoStaircase,
    GeoWall,
    GeoWindow,
)
from app.models.validation import ValidationReport, ValidationResult


def _create_single_floor_geometry() -> Geometry:
    """Create rich single-floor test geometry."""
    return Geometry(
        plot_polygon=[(0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0)],
        buildable_polygon=[(2.0, 2.0), (18.0, 2.0), (18.0, 13.0), (2.0, 13.0)],
        rooms=[
            GeoRoom(
                id="r_living",
                room_type="living",
                usable_polygon=[(2.0, 2.0), (10.0, 2.0), (10.0, 8.0), (2.0, 8.0)],
                area_sqm=48.0,
            ),
            GeoRoom(
                id="r_kitchen",
                room_type="kitchen",
                usable_polygon=[(10.0, 2.0), (18.0, 2.0), (18.0, 8.0), (10.0, 8.0)],
                area_sqm=48.0,
            ),
        ],
        walls=[
            GeoWall(
                id="w_ext_south",
                start=(2.0, 2.0),
                end=(18.0, 2.0),
                type="exterior",
                polygon=[(2.0, 1.85), (18.0, 1.85), (18.0, 2.15), (2.0, 2.15)],
            ),
            GeoWall(
                id="w_int_div",
                start=(10.0, 2.0),
                end=(10.0, 8.0),
                type="interior",
                polygon=[(9.9, 2.0), (10.1, 2.0), (10.1, 8.0), (9.9, 8.0)],
            ),
        ],
        doors=[
            GeoDoor(
                id="d_main",
                wall_id="w_ext_south",
                position=(6.0, 2.0),
                width=1.0,
                type="entrance",
                swing_arc=[
                    (6.0, 2.0),  # hinge
                    (6.0, 3.0),  # open leaf
                    (6.38, 2.92),
                    (6.71, 2.71),
                    (6.92, 2.38),
                    (7.0, 2.0),
                ],
            ),
        ],
        windows=[
            GeoWindow(
                id="win_living",
                wall_id="w_ext_south",
                position=(4.0, 2.0),
                width=1.4,
            ),
        ],
        staircases=[
            GeoStaircase(
                id="stair_main",
                polygon=[(14.0, 4.0), (17.0, 4.0), (17.0, 7.0), (14.0, 7.0)],
                from_floor=1,
                to_floor=2,
                riser_count=12,
            ),
        ],
    )


def test_dxf_export_success_single_floor(tmp_path: Path):
    """Verify DXF export succeeds, creates non-empty file, and parses cleanly."""
    geom = _create_single_floor_geometry()
    fp = FloorPlan(
        id="fp_1",
        floor_number=1,
        project_name="Single Floor DXF Test",
        geometry=geom,
        is_valid=True,
    )
    fps = FloorPlanSet(
        id="fps_1",
        project_name="Single Floor DXF Test",
        plot_boundary=geom.plot_polygon,
        buildable_boundary=geom.buildable_polygon,
        floor_plans=[fp],
    )

    out_file = tmp_path / "test_floorplan.dxf"
    result_path = export_floor_plan_set_to_dxf(fps, out_file, project_name="Single Floor DXF Test")

    # 1. File exists and non-empty
    assert result_path.exists()
    assert result_path.stat().st_size > 0

    # 2. Can be parsed/read by ezdxf
    doc = ezdxf.readfile(str(result_path))
    assert doc is not None

    msp = doc.modelspace()
    entities = list(msp)
    assert len(entities) > 0

    # 3. Check presence of essential layers
    layers_in_doc = {layer.dxf.name for layer in doc.layers}
    assert LAYER_PLOT_BOUNDARY in layers_in_doc
    assert LAYER_BUILDABLE_BOUNDARY in layers_in_doc
    assert LAYER_WALLS_EXTERIOR in layers_in_doc
    assert LAYER_WALLS_INTERIOR in layers_in_doc
    assert LAYER_ROOM_BOUNDARIES in layers_in_doc
    assert LAYER_DOORS in layers_in_doc
    assert LAYER_DOOR_SWINGS in layers_in_doc
    assert LAYER_WINDOWS in layers_in_doc
    assert LAYER_STAIRCASES in layers_in_doc
    assert LAYER_ROOM_LABELS in layers_in_doc
    assert LAYER_DIMENSIONS in layers_in_doc


def test_dxf_plot_and_buildable_boundaries(tmp_path: Path):
    """Verify plot and buildable boundaries are properly exported with correct coordinates."""
    geom = _create_single_floor_geometry()
    fps = FloorPlanSet(
        id="fps_plot",
        plot_boundary=[(0.0, 0.0), (30.0, 0.0), (30.0, 20.0), (0.0, 20.0)],
        buildable_boundary=[(3.0, 3.0), (27.0, 3.0), (27.0, 17.0), (3.0, 17.0)],
        floor_plans=[FloorPlan(id="fp1", floor_number=1, geometry=geom, is_valid=True)],
    )

    out_file = tmp_path / "boundaries.dxf"
    export_floor_plan_set_to_dxf(fps, out_file)

    doc = ezdxf.readfile(str(out_file))
    msp = doc.modelspace()

    plot_entities = [e for e in msp if e.dxf.layer == LAYER_PLOT_BOUNDARY]
    assert len(plot_entities) == 1
    plot_poly = plot_entities[0]
    assert plot_poly.dxftype() == "LWPOLYLINE"
    assert plot_poly.closed is True
    # Verify 4 vertices
    pts = list(plot_poly.get_points(format="xy"))
    assert len(pts) == 4
    assert pts[0] == (0.0, 0.0)
    assert pts[1] == (30.0, 0.0)

    build_entities = [e for e in msp if e.dxf.layer == LAYER_BUILDABLE_BOUNDARY]
    assert len(build_entities) == 1
    build_poly = build_entities[0]
    assert build_poly.dxftype() == "LWPOLYLINE"
    b_pts = list(build_poly.get_points(format="xy"))
    assert len(b_pts) == 4
    assert b_pts[0] == (3.0, 3.0)


def test_dxf_irregular_plot_preservation(tmp_path: Path):
    """Verify irregular plot polygon vertices are preserved exactly without bounding box replacement."""
    l_shaped_plot = [
        (0.0, 0.0),
        (25.0, 0.0),
        (25.0, 12.0),
        (12.0, 12.0),
        (12.0, 22.0),
        (0.0, 22.0),
    ]
    geom = Geometry(
        plot_polygon=l_shaped_plot,
        rooms=[
            GeoRoom(
                id="r1",
                room_type="studio",
                usable_polygon=[(2.0, 2.0), (10.0, 2.0), (10.0, 10.0), (2.0, 10.0)],
                area_sqm=64.0,
            ),
        ],
    )
    fps = FloorPlanSet(
        id="fps_lshape",
        plot_boundary=l_shaped_plot,
        floor_plans=[FloorPlan(id="fp1", floor_number=1, geometry=geom, is_valid=True)],
    )

    out_file = tmp_path / "irregular.dxf"
    export_floor_plan_set_to_dxf(fps, out_file)

    doc = ezdxf.readfile(str(out_file))
    msp = doc.modelspace()

    plot_entities = [e for e in msp if e.dxf.layer == LAYER_PLOT_BOUNDARY]
    assert len(plot_entities) == 1
    plot_poly = plot_entities[0]
    pts = list(plot_poly.get_points(format="xy"))

    assert len(pts) == 6, "Must preserve all 6 vertices of the L-shaped plot polygon"
    for expected_pt, actual_pt in zip(l_shaped_plot, pts):
        assert math.isclose(expected_pt[0], actual_pt[0], abs_tol=1e-3)
        assert math.isclose(expected_pt[1], actual_pt[1], abs_tol=1e-3)


def test_dxf_wall_doors_windows_staircases(tmp_path: Path):
    """Verify walls, doors, swing arcs, windows, and staircases are exported on designated layers."""
    geom = _create_single_floor_geometry()
    fps = FloorPlanSet(
        id="fps_entities",
        floor_plans=[FloorPlan(id="fp1", floor_number=1, geometry=geom, is_valid=True)],
    )

    out_file = tmp_path / "entities.dxf"
    export_floor_plan_set_to_dxf(fps, out_file)

    doc = ezdxf.readfile(str(out_file))
    msp = doc.modelspace()

    # Walls: exterior and interior
    ext_walls = [e for e in msp if e.dxf.layer == LAYER_WALLS_EXTERIOR]
    int_walls = [e for e in msp if e.dxf.layer == LAYER_WALLS_INTERIOR]
    assert len(ext_walls) >= 1
    assert len(int_walls) >= 1
    assert ext_walls[0].dxftype() == "LWPOLYLINE"

    # Doors and Door Swings
    doors = [e for e in msp if e.dxf.layer == LAYER_DOORS]
    swings = [e for e in msp if e.dxf.layer == LAYER_DOOR_SWINGS]
    assert len(doors) >= 1
    assert len(swings) >= 1
    assert swings[0].dxftype() == "LWPOLYLINE"
    assert swings[0].closed is False

    # Windows
    windows = [e for e in msp if e.dxf.layer == LAYER_WINDOWS]
    assert len(windows) >= 1

    # Staircases
    stairs = [e for e in msp if e.dxf.layer == LAYER_STAIRCASES]
    assert len(stairs) >= 1
    # Check footprint polygon exists
    stair_polys = [e for e in stairs if e.dxftype() == "LWPOLYLINE"]
    assert len(stair_polys) >= 1
    # Check tread lines exist
    stair_lines = [e for e in stairs if e.dxftype() == "LINE"]
    assert len(stair_lines) >= 8

    # Room Labels
    labels = [e for e in msp if e.dxf.layer == LAYER_ROOM_LABELS]
    assert len(labels) >= 2


def test_dxf_multi_floor_export(tmp_path: Path):
    """Verify multi-floor projects export with clearly separated floor layers."""
    geom1 = _create_single_floor_geometry()
    geom2 = Geometry(
        rooms=[
            GeoRoom(
                id="r_master_f2",
                room_type="master_bedroom",
                usable_polygon=[(2.0, 2.0), (10.0, 2.0), (10.0, 8.0), (2.0, 8.0)],
                area_sqm=48.0,
            ),
        ],
        walls=[
            GeoWall(
                id="w_ext_f2",
                start=(2.0, 2.0),
                end=(10.0, 2.0),
                type="exterior",
                polygon=[(2.0, 1.85), (10.0, 1.85), (10.0, 2.15), (2.0, 2.15)],
            ),
        ],
    )

    fps = FloorPlanSet(
        id="fps_multi",
        project_name="Duplex Villa",
        plot_boundary=geom1.plot_polygon,
        buildable_boundary=geom1.buildable_polygon,
        floor_plans=[
            FloorPlan(id="fp_1", floor_number=1, geometry=geom1, is_valid=True),
            FloorPlan(id="fp_2", floor_number=2, geometry=geom2, is_valid=True),
        ],
    )

    out_file = tmp_path / "duplex.dxf"
    export_floor_plan_set_to_dxf(fps, out_file, project_name="Duplex Villa")

    doc = ezdxf.readfile(str(out_file))
    layers = {l.dxf.name for l in doc.layers}

    # Verify floor-specific layers exist
    assert "FLOOR_1_WALLS_EXTERIOR" in layers
    assert "FLOOR_1_ROOM_BOUNDARIES" in layers
    assert "FLOOR_1_DOORS" in layers
    assert "FLOOR_2_WALLS_EXTERIOR" in layers
    assert "FLOOR_2_ROOM_BOUNDARIES" in layers

    # Global plot boundary remains un-prefixed
    assert LAYER_PLOT_BOUNDARY in layers


def test_dxf_rejects_invalid_floor_plan(tmp_path: Path):
    """Verify DXF exporter rejects invalid floor plans (Requirement 15)."""
    geom = _create_single_floor_geometry()
    fps = FloorPlanSet(
        id="fps_invalid",
        floor_plans=[FloorPlan(id="fp1", floor_number=1, geometry=geom, is_valid=False)],
        validation_report=ValidationReport(results=[ValidationResult(is_valid=False)]),
    )

    out_file = tmp_path / "invalid.dxf"
    exporter = DXFExporter()
    with pytest.raises(InvalidExportInputError, match="validation"):
        exporter.export_floor_plan_set(fps, out_file)


def test_dxf_coordinate_fidelity(tmp_path: Path):
    """Verify exported DXF coordinates match source Geometry Engine coordinates exactly."""
    geom = _create_single_floor_geometry()
    fps = FloorPlanSet(
        id="fps_prec",
        plot_boundary=[(1.234, 5.678), (21.234, 5.678), (21.234, 15.678), (1.234, 15.678)],
        floor_plans=[FloorPlan(id="fp1", floor_number=1, geometry=geom, is_valid=True)],
    )

    out_file = tmp_path / "coords.dxf"
    export_floor_plan_set_to_dxf(fps, out_file)

    doc = ezdxf.readfile(str(out_file))
    msp = doc.modelspace()

    plot_entities = [e for e in msp if e.dxf.layer == LAYER_PLOT_BOUNDARY]
    pts = list(plot_entities[0].get_points(format="xy"))

    for orig_pt, dxf_pt in zip(fps.plot_boundary, pts):
        assert math.isclose(orig_pt[0], dxf_pt[0], abs_tol=1e-3)
        assert math.isclose(orig_pt[1], dxf_pt[1], abs_tol=1e-3)


def test_dxf_export_determinism(tmp_path: Path):
    """Verify that exporting the same FloorPlanSet twice produces equivalent entity structures."""
    geom = _create_single_floor_geometry()
    fps = FloorPlanSet(
        id="fps_det",
        plot_boundary=geom.plot_polygon,
        floor_plans=[FloorPlan(id="fp1", floor_number=1, geometry=geom, is_valid=True)],
    )

    out1 = tmp_path / "run1.dxf"
    out2 = tmp_path / "run2.dxf"

    export_floor_plan_set_to_dxf(fps, out1)
    export_floor_plan_set_to_dxf(fps, out2)

    doc1 = ezdxf.readfile(str(out1))
    doc2 = ezdxf.readfile(str(out2))

    entities1 = list(doc1.modelspace())
    entities2 = list(doc2.modelspace())

    assert len(entities1) == len(entities2)
    for e1, e2 in zip(entities1, entities2):
        assert e1.dxftype() == e2.dxftype()
        assert e1.dxf.layer == e2.dxf.layer


def test_dxf_filename_sanitization():
    """Verify filename generation and sanitization helpers."""
    assert sanitize_project_name("Modern Villa 2026!") == "modern_villa_2026"
    assert sanitize_project_name("Project / Test : CAD?") == "project_test_cad"

    assert get_dxf_filename("Modern Villa", is_multi_floor=False) == "modern_villa_floorplan.dxf"
    assert get_dxf_filename("Modern Villa", is_multi_floor=True) == "modern_villa_floorplans.dxf"
    assert get_dxf_filename("", is_multi_floor=False) == "floorplan.dxf"
    assert get_dxf_filename("", is_multi_floor=True) == "floorplans.dxf"
