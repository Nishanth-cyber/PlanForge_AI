"""Unit tests for PolygonBuilder: rectangular, square, L-shaped, and irregular shapes."""

import pytest
from app.geometry.exceptions import (
    ImpossibleDimensionsError,
    InvalidShapeParametersError,
    RoomOutOfBoundsError,
)
from app.geometry.geometry_utils import polygon_area
from app.geometry.polygon_builder import PolygonBuilder


def test_construct_rectangle_success():
    """Verify rectangular polygon generation within region bounds."""
    region = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    rect = PolygonBuilder.construct_rectangle(region, width=4.0, length=5.0, anchor="center")
    assert len(rect) == 4
    assert pytest.approx(polygon_area(rect), 0.01) == 20.0
    # Coordinates centered in (0..10, 0..10) -> (3..7, 2.5..7.5)
    xs = [p[0] for p in rect]
    ys = [p[1] for p in rect]
    assert min(xs) == 3.0
    assert max(xs) == 7.0
    assert min(ys) == 2.5
    assert max(ys) == 7.5


def test_construct_rectangle_south_west():
    """Verify rectangular polygon generation with south_west anchor."""
    region = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)]
    rect = PolygonBuilder.construct_rectangle(region, width=3.0, length=4.0, anchor="south_west")
    assert len(rect) == 4
    xs = [p[0] for p in rect]
    ys = [p[1] for p in rect]
    assert min(xs) == 2.0
    assert max(xs) == 5.0
    assert min(ys) == 2.0
    assert max(ys) == 6.0


def test_construct_rectangle_exceeds_bounds():
    """Verify ImpossibleDimensionsError when dimensions exceed region envelope."""
    region = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    with pytest.raises(ImpossibleDimensionsError):
        PolygonBuilder.construct_rectangle(region, width=6.0, length=4.0)


def test_construct_square_success():
    """Verify square polygon generation."""
    region = [(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0)]
    sq = PolygonBuilder.construct_square(region, area=16.0)
    assert len(sq) == 4
    assert pytest.approx(polygon_area(sq), 0.01) == 16.0


def test_construct_l_shaped_success():
    """Verify orthogonal 6-vertex L-shaped polygon generation."""
    region = [(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0)]
    l_poly = PolygonBuilder.construct_l_shaped(region, cutout_quadrant="north_east")
    assert len(l_poly) == 6
    area = polygon_area(l_poly)
    assert 0 < area < 36.0


def test_construct_l_shaped_invalid_cutouts():
    """Verify InvalidShapeParametersError when cutouts exceed envelope."""
    region = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    with pytest.raises(InvalidShapeParametersError):
        PolygonBuilder.construct_l_shaped(region, w2=6.0, l2=6.0)


def test_construct_from_intent_fallback():
    """Verify construct_from_intent returns region directly for custom or default shapes."""
    region = [(1.0, 1.0), (4.0, 1.0), (4.0, 5.0), (1.0, 5.0)]
    res = PolygonBuilder.construct_from_intent("custom", region)
    assert res == region


def test_extract_largest_polygon_and_geometry_collection():
    """Verify extract_largest_polygon safely handles GeometryCollection and MultiPolygon."""
    from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
    from app.geometry.geometry_utils import extract_largest_polygon, from_shapely_polygon

    poly1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    line = LineString([(0, 0), (10, 10)])
    pt = Point(5, 5)

    # Mixed GeometryCollection
    geom_col = GeometryCollection([poly1, line, pt])
    extracted = extract_largest_polygon(geom_col)
    assert isinstance(extracted, Polygon)
    assert extracted.area == 100.0

    # from_shapely_polygon handles GeometryCollection without AttributeError on .exterior
    coords = from_shapely_polygon(geom_col)
    assert len(coords) == 4
    assert (0.0, 0.0) in coords
    assert (10.0, 10.0) in coords

    # Empty GeometryCollection returns empty polygon and coords
    empty_col = GeometryCollection([])
    assert extract_largest_polygon(empty_col).is_empty
    assert from_shapely_polygon(empty_col) == []

