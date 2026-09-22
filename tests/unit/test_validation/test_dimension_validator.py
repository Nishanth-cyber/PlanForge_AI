"""Unit tests for DimensionValidator: minimum area violations and soft warnings."""

import pytest
from app.models.geometry import Geometry, GeoRoom
from app.models.planning import FloorPlanSpec, RoomSpec
from app.validation.dimension_validator import DimensionValidator


def test_dimension_validator_compliant_room():
    """Verify compliant usable room area produces no errors."""
    room = GeoRoom(
        id="r1",
        room_type="living",
        area_sqm=20.0,
        built_polygon=[(0, 0), (5, 0), (5, 4.5), (0, 4.5)],
        usable_polygon=[(0.1, 0.1), (4.9, 0.1), (4.9, 4.4), (0.1, 4.4)],
    )
    geom = Geometry(rooms=[room], floor_number=1)
    spec = FloorPlanSpec(
        floor_number=1,
        room_specs=[RoomSpec(room_type="living", min_area_sqm=15.0, target_area_sqm=20.0)],
    )

    val = DimensionValidator()
    issues = val.validate(geom, floor_plan_spec=spec)
    assert len(issues) == 0


def test_dimension_validator_hard_minimum_violation():
    """Verify hard error when usable area is below minimum requirement."""
    # Living room requires at least 18 sqm, but actual usable area is only 12 sqm
    room = GeoRoom(
        id="r_small",
        room_type="living",
        area_sqm=12.0,
    )
    geom = Geometry(rooms=[room], floor_number=1)
    spec = FloorPlanSpec(
        floor_number=1,
        room_specs=[RoomSpec(room_type="living", min_area_sqm=18.0)],
    )

    val = DimensionValidator()
    issues = val.validate(geom, floor_plan_spec=spec)

    assert len(issues) >= 1
    assert issues[0].severity == "error"
    assert issues[0].check == "minimum_area"
    assert "below hard minimum" in issues[0].message


def test_dimension_validator_soft_target_warning():
    """Verify warning (not error) when area deviates substantially from target."""
    room = GeoRoom(
        id="r_warn",
        room_type="study",
        area_sqm=6.0,  # Target is 12.0, deviation is 50%
    )
    geom = Geometry(rooms=[room], floor_number=1)
    spec = FloorPlanSpec(
        floor_number=1,
        room_specs=[RoomSpec(room_type="study", min_area_sqm=5.0, target_area_sqm=12.0)],
    )

    val = DimensionValidator()
    issues = val.validate(geom, floor_plan_spec=spec)

    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].check == "target_area_undersize"
