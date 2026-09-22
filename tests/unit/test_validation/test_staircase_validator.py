"""Unit tests for StaircaseValidator: missing core, allocation containment, and multi-floor alignment."""

import pytest
from app.models.allocation import AllocatedRegion, Allocation
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoStaircase
from app.validation.staircase_validator import StaircaseValidator


def test_missing_required_staircase_error():
    """Verify error when vertical circulation is required on multi-floor building but missing."""
    geom = Geometry(staircases=[], floor_number=1)
    val = StaircaseValidator()

    issues = val.validate_floor(geom, is_staircase_required=True)
    assert len(issues) >= 1
    assert issues[0].check == "missing_staircase"


def test_staircase_outside_allocation_error():
    """Verify error when staircase footprint spills outside ASAA staircase allocation."""
    stair_reg = AllocatedRegion(
        id="reg_stair_f1",
        room_type="staircase",
        zone_type="staircase",
        polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 4.0), (0.0, 4.0)],
    )
    alloc = Allocation(floor_number=1, allocated_regions=[stair_reg])

    # Staircase placed at (2..6, 0..4) -> spills outside allocation
    stair = GeoStaircase(
        id="stair_1",
        polygon=[(2.0, 0.0), (6.0, 0.0), (6.0, 4.0), (2.0, 4.0)],
        riser_count=16,
        tread_depth=0.28,
    )
    geom = Geometry(staircases=[stair], floor_number=1)

    val = StaircaseValidator()
    issues = val.validate_floor(geom, allocation=alloc, is_staircase_required=True)

    assert any(i.check == "staircase_allocation_containment" for i in issues)


def test_vertical_staircase_misalignment_error():
    """Verify error when staircase coordinates between Floor 1 and Floor 2 do not align."""
    stair_f1 = GeoStaircase(id="stair_f1", polygon=[(0, 0), (2, 0), (2, 4), (0, 4)])
    stair_f2 = GeoStaircase(id="stair_f2", polygon=[(5, 5), (7, 5), (7, 9), (5, 9)])  # Completely shifted!

    fp1 = FloorPlan(floor_number=1, geometry=Geometry(staircases=[stair_f1], floor_number=1))
    fp2 = FloorPlan(floor_number=2, geometry=Geometry(staircases=[stair_f2], floor_number=2))
    fps = FloorPlanSet(floor_plans=[fp1, fp2])

    val = StaircaseValidator()
    issues = val.validate_multi_floor_alignment(fps)

    assert len(issues) >= 1
    assert issues[0].severity == "error"
    assert issues[0].check == "vertical_staircase_misalignment"
    assert "vertical core is misaligned" in issues[0].message


def test_vertical_staircase_aligned_passes():
    """Verify perfectly aligned multi-floor staircases produce zero misalignment errors."""
    stair_f1 = GeoStaircase(id="stair_f1", polygon=[(1, 1), (3, 1), (3, 5), (1, 5)])
    stair_f2 = GeoStaircase(id="stair_f2", polygon=[(1, 1), (3, 1), (3, 5), (1, 5)])

    fp1 = FloorPlan(floor_number=1, geometry=Geometry(staircases=[stair_f1], floor_number=1))
    fp2 = FloorPlan(floor_number=2, geometry=Geometry(staircases=[stair_f2], floor_number=2))
    fps = FloorPlanSet(floor_plans=[fp1, fp2])

    val = StaircaseValidator()
    issues = val.validate_multi_floor_alignment(fps)
    assert len(issues) == 0
