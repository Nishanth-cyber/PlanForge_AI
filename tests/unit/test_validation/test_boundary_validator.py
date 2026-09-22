"""Unit tests for BoundaryValidator: plot and buildable envelope verification."""

import pytest
from app.models.geometry import Geometry, GeoRoom, GeoStaircase
from app.validation.boundary_validator import BoundaryValidator


def test_boundary_validator_clean_containment():
    """Verify clean floor geometry passes boundary checks without issues."""
    room = GeoRoom(
        id="room_1",
        room_type="living",
        built_polygon=[(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)],
        floor_number=1,
    )
    geom = Geometry(rooms=[room], floor_number=1)

    plot = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    buildable = [(0.5, 0.5), (9.5, 0.5), (9.5, 9.5), (0.5, 9.5)]

    val = BoundaryValidator()
    issues = val.validate(geom, plot_boundary=plot, buildable_boundary=buildable)
    assert len(issues) == 0


def test_boundary_validator_plot_spill_error():
    """Verify error when room extends outside plot boundary."""
    room = GeoRoom(
        id="room_spill",
        room_type="living",
        built_polygon=[(8.0, 8.0), (12.0, 8.0), (12.0, 12.0), (8.0, 12.0)],  # Spills outside (0..10, 0..10)
        floor_number=1,
    )
    geom = Geometry(rooms=[room], floor_number=1)
    plot = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]

    val = BoundaryValidator()
    issues = val.validate(geom, plot_boundary=plot)
    assert len(issues) >= 1
    assert issues[0].severity == "error"
    assert issues[0].category == "boundary"
    assert issues[0].check == "plot_boundary_containment"
    assert issues[0].target_id == "room_spill"


def test_boundary_validator_buildable_setback_spill():
    """Verify error when room extends outside buildable envelope into setback."""
    room = GeoRoom(
        id="room_setback",
        room_type="bedroom",
        built_polygon=[(0.5, 0.5), (4.0, 0.5), (4.0, 4.0), (0.5, 4.0)],
        floor_number=1,
    )
    geom = Geometry(rooms=[room], floor_number=1)

    plot = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    # Setback = 2.0m -> buildable = (2..8, 2..8)
    buildable = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)]

    val = BoundaryValidator()
    issues = val.validate(geom, plot_boundary=plot, buildable_boundary=buildable)
    assert len(issues) >= 1
    assert any(i.check == "buildable_boundary_containment" for i in issues)


def test_boundary_validator_irregular_l_shaped_plot():
    """Verify true polygonal containment check on 6-vertex L-shaped plot."""
    l_buildable = [
        (1.0, 1.0),
        (15.0, 1.0),
        (15.0, 8.0),
        (8.0, 8.0),
        (8.0, 15.0),
        (1.0, 15.0),
    ]

    # Room in cutout quadrant (10..14, 10..14) -> outside L-shape!
    room_in_cutout = GeoRoom(
        id="room_cutout",
        room_type="study",
        built_polygon=[(10.0, 10.0), (13.0, 10.0), (13.0, 13.0), (10.0, 13.0)],
        floor_number=1,
    )
    geom = Geometry(rooms=[room_in_cutout], floor_number=1)

    val = BoundaryValidator()
    issues = val.validate(geom, buildable_boundary=l_buildable)
    assert len(issues) >= 1
    assert any(i.check == "buildable_boundary_containment" for i in issues)
