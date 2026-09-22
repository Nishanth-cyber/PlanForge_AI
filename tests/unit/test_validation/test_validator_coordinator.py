"""Unit tests for FloorPlanValidator coordinator."""

import pytest
from app.models.geometry import Geometry, GeoRoom, GeoWall, GeoDoor, GeoStaircase
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.validation.validator import FloorPlanValidator, Validator


def test_validator_sets_floor_plan_state():
    """Verify that validating a floor updates floor_plan.validation and floor_plan.is_valid."""
    r1 = GeoRoom(id="r_living", room_type="living", usable_polygon=[(1, 1), (6, 1), (6, 6), (1, 6)], area_sqm=25.0)
    w_ext = GeoWall(id="w_ext", start=(1, 1), end=(6, 1), type="exterior", room_ids=["r_living"])
    d_ext = GeoDoor(id="d_ext", wall_id="w_ext", position=(3.5, 1), type="entrance")

    geom = Geometry(
        floor_number=1,
        rooms=[r1],
        walls=[w_ext],
        doors=[d_ext],
        plot_polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
        buildable_polygon=[(0.5, 0.5), (9.5, 0.5), (9.5, 9.5), (0.5, 9.5)],
    )
    fp = FloorPlan(floor_number=1, geometry=geom)
    assert fp.is_valid is False
    assert fp.validation is None

    validator = FloorPlanValidator()
    result = validator.validate_floor(fp)

    assert fp.validation is result
    assert fp.is_valid is True
    assert result.is_valid is True
    assert result.error_count == 0


def test_validator_hard_error_invalidates():
    """Verify that a hard error (e.g. boundary violation) invalidates the floor and floor set."""
    # Room extends outside plot
    r1 = GeoRoom(id="r_living", room_type="living", usable_polygon=[(5, 5), (15, 5), (15, 15), (5, 15)], area_sqm=100.0)
    w_ext = GeoWall(id="w_ext", start=(5, 5), end=(15, 5), type="exterior", room_ids=["r_living"])
    d_ext = GeoDoor(id="d_ext", wall_id="w_ext", position=(10, 5), type="entrance")

    geom = Geometry(
        floor_number=1,
        rooms=[r1],
        walls=[w_ext],
        doors=[d_ext],
        plot_polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
        buildable_polygon=[(0.5, 0.5), (9.5, 0.5), (9.5, 9.5), (0.5, 9.5)],
    )
    fp = FloorPlan(floor_number=1, geometry=geom)
    fp_set = FloorPlanSet(floor_plans=[fp])

    validator = Validator()
    report = validator.validate(fp_set)

    assert report.overall_valid is False
    assert fp.is_valid is False
    assert report.results[0].error_count > 0
    assert any(i.check == "buildable_boundary_containment" for i in report.all_issues())


def test_validator_warning_tolerance():
    """Verify that soft warnings do NOT invalidate the floor or floor plan set."""
    # Target area deviation triggers a warning, not an error
    r1 = GeoRoom(id="r_living", room_type="living", usable_polygon=[(1, 1), (5, 1), (5, 5), (1, 5)], area_sqm=16.0)
    w_ext = GeoWall(id="w_ext", start=(1, 1), end=(5, 1), type="exterior", room_ids=["r_living"])
    d_ext = GeoDoor(id="d_ext", wall_id="w_ext", position=(3.0, 1), type="entrance")

    geom = Geometry(
        floor_number=1,
        rooms=[r1],
        walls=[w_ext],
        doors=[d_ext],
        plot_polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
        buildable_polygon=[(0.5, 0.5), (9.5, 0.5), (9.5, 9.5), (0.5, 9.5)],
    )
    fp = FloorPlan(floor_number=1, geometry=geom)
    fp_set = FloorPlanSet(floor_plans=[fp])

    # Requirements: min_area 10 (satisfied: 16 > 10), but preferred_area 30 (deviation > 30% -> warning)
    reqs = Requirements(
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_area_sqm=10.0, preferred_area_sqm=30.0)
                ]
            )
        ]
    )

    validator = FloorPlanValidator()
    report = validator.validate(fp_set, requirements=reqs)

    assert report.overall_valid is True
    assert fp.is_valid is True
    assert report.results[0].error_count == 0
    assert report.results[0].warning_count >= 1
    assert any(i.severity == "warning" and i.check == "target_area_undersize" for i in report.all_issues())


def test_validator_score_calculation():
    """Verify deterministic score calculation penalizing errors and warnings."""
    r1 = GeoRoom(id="r_living", room_type="living", usable_polygon=[(1, 1), (5, 1), (5, 5), (1, 5)], area_sqm=16.0)
    geom = Geometry(
        floor_number=1,
        rooms=[r1],
        plot_polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
    )
    fp = FloorPlan(floor_number=1, geometry=geom)

    validator = FloorPlanValidator()
    result = validator.validate_floor(fp)

    # Missing entrance connection and isolated room errors
    assert result.error_count > 0
    expected_score = max(0.0, 100.0 - (15.0 * result.error_count) - (3.0 * result.warning_count))
    assert result.score == pytest.approx(expected_score)
