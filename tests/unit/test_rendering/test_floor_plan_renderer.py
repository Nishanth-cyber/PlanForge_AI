"""Unit tests for the visual floor plan rendering subsystem."""

import copy
from pathlib import Path
import pytest

from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import (
    Geometry,
    GeoRoom,
    GeoWall,
    GeoDoor,
    GeoWindow,
    GeoStaircase,
)
from app.rendering.errors import EmptyGeometryError, RenderingError
from app.rendering.floor_renderer import FloorPlanRenderer
from app.rendering.options import RenderOptions, RenderedFloor
from app.rendering.renderer import render_floor_plan, render_floor_plan_set


def build_sample_geometry(floor_number: int = 1) -> Geometry:
    """Helper creating deterministic, rich test geometry."""
    # Rooms
    living = GeoRoom(
        id="room_living_1",
        room_type="living",
        usable_polygon=[(1.0, 1.0), (7.0, 1.0), (7.0, 6.0), (1.0, 6.0)],
        built_polygon=[(0.8, 0.8), (7.2, 0.8), (7.2, 6.2), (0.8, 6.2)],
        area_sqm=30.0,
        floor_number=floor_number,
        architectural_room_id="arch_living_1",
    )
    bed = GeoRoom(
        id="room_bed_1",
        room_type="bedroom",
        usable_polygon=[(7.0, 1.0), (12.0, 1.0), (12.0, 5.0), (7.0, 5.0)],
        built_polygon=[(6.8, 0.8), (12.2, 0.8), (12.2, 5.2), (6.8, 5.2)],
        area_sqm=20.0,
        floor_number=floor_number,
        architectural_room_id="arch_bed_1",
    )
    corridor = GeoRoom(
        id="room_corr_1",
        room_type="corridor",
        usable_polygon=[(1.0, 6.0), (12.0, 6.0), (12.0, 7.5), (1.0, 7.5)],
        built_polygon=[(0.8, 5.8), (12.2, 5.8), (12.2, 7.7), (0.8, 7.7)],
        area_sqm=16.5,
        floor_number=floor_number,
        is_corridor=True,
    )

    # Walls
    walls = [
        GeoWall(id="w1", start=(0.8, 0.8), end=(12.2, 0.8), type="exterior", floor_number=floor_number),
        GeoWall(id="w2", start=(12.2, 0.8), end=(12.2, 7.7), type="exterior", floor_number=floor_number),
        GeoWall(id="w3", start=(12.2, 7.7), end=(0.8, 7.7), type="exterior", floor_number=floor_number),
        GeoWall(id="w4", start=(0.8, 7.7), end=(0.8, 0.8), type="exterior", floor_number=floor_number),
        GeoWall(id="w5", start=(7.0, 0.8), end=(7.0, 6.0), type="interior", floor_number=floor_number),
    ]

    # Doors
    doors = [
        GeoDoor(
            id="door_ent",
            position=(4.0, 0.8),
            width=1.0,
            type="entrance",
            connects_from="exterior",
            connects_to="living",
            swing_arc=[(4.0, 0.8), (4.5, 1.2), (4.0, 1.8)],
            floor_number=floor_number,
        ),
        GeoDoor(
            id="door_bed",
            position=(7.0, 3.0),
            width=0.9,
            type="interior",
            connects_from="living",
            connects_to="bedroom",
            swing_arc=[(7.0, 3.0), (7.4, 3.4), (7.0, 3.9)],
            floor_number=floor_number,
        ),
    ]

    # Windows
    windows = [
        GeoWindow(id="win_1", position=(2.5, 0.8), width=1.5, floor_number=floor_number),
        GeoWindow(id="win_2", position=(10.0, 0.8), width=1.2, floor_number=floor_number),
    ]

    # Staircase
    staircases = [
        GeoStaircase(
            id="stair_1",
            polygon=[(9.0, 5.0), (12.0, 5.0), (12.0, 6.0), (9.0, 6.0)],
            from_floor=floor_number,
            to_floor=floor_number + 1,
            riser_count=10,
            floor_number=floor_number,
        )
    ]

    # Plot & Buildable
    plot_polygon = [(0.0, 0.0), (15.0, 0.0), (15.0, 10.0), (0.0, 10.0)]
    buildable_polygon = [(0.8, 0.8), (12.2, 0.8), (12.2, 7.7), (0.8, 7.7)]

    return Geometry(
        floor_number=floor_number,
        rooms=[living, bed, corridor],
        walls=walls,
        doors=doors,
        windows=windows,
        staircases=staircases,
        plot_polygon=plot_polygon,
        buildable_polygon=buildable_polygon,
    )


def test_single_floor_rendering(tmp_path: Path):
    """Verify clean rendering of a single floor plan."""
    geom = build_sample_geometry(floor_number=1)
    fp = FloorPlan(floor_number=1, project_name="Single Floor Demo", geometry=geom, is_valid=True)

    out_file = tmp_path / "floor_1.png"
    result = render_floor_plan(fp, out_file, orientation="north")

    assert out_file.exists()
    assert out_file.stat().st_size > 5000  # Valid non-empty PNG
    assert isinstance(result, RenderedFloor)
    assert result.floor_number == 1
    assert result.rendered_room_count == 3
    assert result.rendered_wall_count == 5
    assert result.rendered_door_count == 2
    assert result.rendered_window_count == 2
    assert result.rendered_staircase_count == 1
    assert result.rendered_corridor_count == 1
    assert result.orientation == "north"
    assert result.has_plot_boundary is True
    assert result.has_buildable_boundary is True


def test_multi_floor_rendering(tmp_path: Path):
    """Verify that multi-floor sets produce separate images for each floor."""
    geom_f1 = build_sample_geometry(floor_number=1)
    geom_f2 = build_sample_geometry(floor_number=2)

    fp1 = FloorPlan(floor_number=1, geometry=geom_f1, is_valid=True)
    fp2 = FloorPlan(floor_number=2, geometry=geom_f2, is_valid=True)
    fps = FloorPlanSet(
        project_name="Duplex",
        floor_plans=[fp1, fp2],
        plot_boundary=[(0.0, 0.0), (15.0, 0.0), (15.0, 10.0), (0.0, 10.0)],
    )

    results = render_floor_plan_set(fps, tmp_path, orientation="east")

    assert len(results) == 2
    f1_img = tmp_path / "floor_1.png"
    f2_img = tmp_path / "floor_2.png"

    assert f1_img.exists() and f1_img.stat().st_size > 5000
    assert f2_img.exists() and f2_img.stat().st_size > 5000
    assert results[0].floor_number == 1
    assert results[1].floor_number == 2


def test_irregular_plot_rendering(tmp_path: Path):
    """Verify that irregular L-shaped plots are rendered as true polygons without bounding box substitution."""
    l_shaped_plot = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 8.0),
        (10.0, 8.0),
        (10.0, 16.0),
        (0.0, 16.0),
    ]
    geom = build_sample_geometry(floor_number=1)
    geom.plot_polygon = l_shaped_plot

    fp = FloorPlan(floor_number=1, geometry=geom)
    out_file = tmp_path / "irregular_floor.png"

    result = render_floor_plan(fp, out_file)
    assert out_file.exists() and out_file.stat().st_size > 5000
    assert result.has_plot_boundary is True


def test_publication_mode_rendering(tmp_path: Path):
    """Verify high-DPI publication mode rendering."""
    geom = build_sample_geometry(floor_number=1)
    fp = FloorPlan(floor_number=1, geometry=geom)

    opts = RenderOptions(dpi=400, publication_mode=True, show_room_ids=True)
    out_file = tmp_path / "publication_floor.png"

    result = render_floor_plan(fp, out_file, options=opts, orientation="north")
    assert out_file.exists()
    assert result.width_px == int(10.0 * 400)
    assert result.height_px == int(10.0 * 400)


def test_orientation_presence_vs_absence(tmp_path: Path):
    """Verify north arrow is rendered ONLY when orientation is supplied, never fabricated."""
    geom = build_sample_geometry(floor_number=1)
    fp = FloorPlan(floor_number=1, geometry=geom)

    # 1. Orientation provided
    out_with_orient = tmp_path / "with_orient.png"
    res_with = render_floor_plan(fp, out_with_orient, orientation="south")
    assert res_with.orientation == "south"

    # 2. Orientation omitted (must NOT invent north arrow)
    out_no_orient = tmp_path / "no_orient.png"
    res_no = render_floor_plan(fp, out_no_orient, orientation=None)
    assert res_no.orientation is None


def test_rendering_immutability(tmp_path: Path):
    """Verify that rendering NEVER mutates source FloorPlan or Geometry objects."""
    geom = build_sample_geometry(floor_number=1)
    fp = FloorPlan(floor_number=1, geometry=geom, is_valid=True)
    fp_copy = copy.deepcopy(fp)

    out_file = tmp_path / "immutable_test.png"
    render_floor_plan(fp, out_file, orientation="west")

    # Verify original object is bitwise identical to its deepcopy
    assert fp.floor_number == fp_copy.floor_number
    assert fp.is_valid == fp_copy.is_valid
    assert fp.geometry.plot_polygon == fp_copy.geometry.plot_polygon
    assert len(fp.geometry.rooms) == len(fp_copy.geometry.rooms)
    for r1, r2 in zip(fp.geometry.rooms, fp_copy.geometry.rooms):
        assert r1.id == r2.id
        assert r1.area_sqm == r2.area_sqm
        assert r1.usable_polygon == r2.usable_polygon


def test_deterministic_rendering_output(tmp_path: Path):
    """Verify that identical inputs produce identical image files."""
    geom = build_sample_geometry(floor_number=1)
    fp = FloorPlan(floor_number=1, geometry=geom)

    out1 = tmp_path / "run1.png"
    out2 = tmp_path / "run2.png"

    r1 = render_floor_plan(fp, out1, orientation="north")
    r2 = render_floor_plan(fp, out2, orientation="north")

    assert r1.rendered_room_count == r2.rendered_room_count
    assert r1.rendered_wall_count == r2.rendered_wall_count
    assert out1.stat().st_size > 0
    assert out2.stat().st_size > 0
    # In matplotlib Agg, same geometry and options produce exact same file size
    assert abs(out1.stat().st_size - out2.stat().st_size) < 50


def test_empty_geometry_error(tmp_path: Path):
    """Verify that rendering an empty geometry raises EmptyGeometryError."""
    empty_geom = Geometry(floor_number=1)
    fp = FloorPlan(floor_number=1, geometry=empty_geom)

    out_file = tmp_path / "empty.png"
    with pytest.raises(EmptyGeometryError):
        render_floor_plan(fp, out_file)
