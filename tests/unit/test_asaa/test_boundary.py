"""Unit tests for ASAA buildable boundary calculation."""

import pytest
from app.asaa.boundary import BuildableBoundaryCalculator
from app.asaa.exceptions import BoundaryConstraintError
from shapely.geometry import Polygon


def test_rectangular_plot_without_setbacks():
    """Test rectangular plot with no setbacks produces buildable boundary equal to plot."""
    bb = BuildableBoundaryCalculator.calculate(
        plot_width_m=15.0,
        plot_depth_m=20.0,
    )
    assert bb.is_rectangular is True
    assert bb.area_sqm == 300.0
    assert bb.bounds == (0.0, 0.0, 15.0, 20.0)
    assert len(bb.polygon) == 4


def test_rectangular_plot_with_setbacks():
    """Test directional setbacks on rectangular plot: front=3m, rear=2m, left=1.5m, right=1.5m."""
    bb = BuildableBoundaryCalculator.calculate(
        plot_width_m=15.0,
        plot_depth_m=20.0,
        setbacks={"front": 3.0, "rear": 2.0, "left": 1.5, "right": 1.5},
    )
    assert bb.is_rectangular is True
    # Width: 15 - 1.5 - 1.5 = 12.0
    # Depth: 20 - 3.0 - 2.0 = 15.0
    # Area: 12 * 15 = 180.0
    assert bb.area_sqm == 180.0
    assert bb.bounds == (1.5, 3.0, 13.5, 18.0)


def test_uniform_setbacks():
    """Test uniform setbacks using 'all' key."""
    bb = BuildableBoundaryCalculator.calculate(
        plot_width_m=20.0,
        plot_depth_m=20.0,
        setbacks={"all": 2.0},
    )
    # Width: 20 - 4 = 16.0, Depth: 20 - 4 = 16.0, Area: 256.0
    assert bb.area_sqm == 256.0
    assert bb.bounds == (2.0, 2.0, 18.0, 18.0)


def test_l_shaped_polygon_preserves_shape():
    """Test that L-shaped plot boundary is preserved and NOT replaced with a bounding box."""
    # L-shaped 6-vertex polygon
    l_points = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 10.0),
        (10.0, 10.0),
        (10.0, 20.0),
        (0.0, 20.0),
    ]
    # L-shape area: 20*10 + 10*10 = 300.0
    bb = BuildableBoundaryCalculator.calculate(
        plot_polygon=l_points,
        setbacks={"all": 1.0},
    )
    assert bb.is_rectangular is False
    # Verify that the buildable polygon has at least 6 vertices or preserves L-shape
    assert len(bb.polygon) >= 6
    # It must NOT be a simple 18x18 bounding box (area would be 324, exceeding L-shape)
    assert bb.area_sqm < 300.0
    # Check that the buildable polygon is strictly inside the original L-shape
    original_poly = Polygon(l_points)
    assert bb.shapely_polygon.within(original_poly)


def test_irregular_polygon_boundary():
    """Test irregular 5-vertex polygon."""
    points = [
        (0.0, 0.0),
        (15.0, 2.0),
        (18.0, 16.0),
        (8.0, 20.0),
        (0.0, 14.0),
    ]
    bb = BuildableBoundaryCalculator.calculate(
        plot_polygon=points,
        setbacks={"all": 1.0},
    )
    assert bb.area_sqm > 0.0
    assert bb.shapely_polygon.within(Polygon(points))


def test_excessive_setbacks_raise_boundary_error():
    """Test that setbacks exceeding plot dimensions raise BoundaryConstraintError."""
    with pytest.raises(BoundaryConstraintError) as exc_info:
        BuildableBoundaryCalculator.calculate(
            plot_width_m=10.0,
            plot_depth_m=10.0,
            setbacks={"left": 6.0, "right": 6.0},  # 12m exceeds 10m width
        )
    assert "eliminate entire buildable area" in str(exc_info.value)
