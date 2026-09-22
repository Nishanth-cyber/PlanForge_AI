"""Unit tests for FloorPlan and FloorPlanSet data contracts."""

from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoRoom
from app.models.validation import ValidationResult, ValidationReport


def test_floor_plan_single_floor():
    """Test single floor plan aggregation of geometry and validation."""
    room = GeoRoom(room_type="studio", area_sqm=35.0)
    geom = Geometry(floor_number=1, rooms=[room])
    val = ValidationResult(floor_number=1, is_valid=True, score=98.0)

    fp = FloorPlan(
        project_name="Studio Apartment",
        floor_number=1,
        geometry=geom,
        validation=val,
        is_valid=True,
    )

    assert fp.id is not None
    assert fp.usable_area() == 35.0
    assert fp.is_valid is True
    assert fp.geometry == geom
    assert fp.validation == val


def test_floor_plan_set_multi_floor_separation():
    """Test FloorPlanSet multi-floor aggregation without Floor-1-only mirroring."""
    g1 = Geometry(floor_number=1, rooms=[GeoRoom(room_type="living", area_sqm=40.0)])
    g2 = Geometry(floor_number=2, rooms=[GeoRoom(room_type="bedroom", area_sqm=20.0)])

    v1 = ValidationResult(floor_number=1, is_valid=True)
    v2 = ValidationResult(floor_number=2, is_valid=True)

    fp1 = FloorPlan(floor_number=1, geometry=g1, validation=v1, is_valid=True)
    fp2 = FloorPlan(floor_number=2, geometry=g2, validation=v2, is_valid=True)

    report = ValidationReport(results=[v1, v2])

    fps = FloorPlanSet(
        project_name="Duplex Villa",
        plot_boundary=[(0.0, 0.0), (10.0, 0.0), (10.0, 15.0), (0.0, 15.0)],
        buildable_boundary=[(1.5, 2.0), (8.5, 2.0), (8.5, 13.0), (1.5, 13.0)],
        floor_plans=[fp1, fp2],
        validation_report=report,
        generation_metadata={"algorithm": "ASAA_v2", "designer": "ArchitecturalLLM"},
    )

    assert fps.all_valid is True
    assert fps.total_usable_area == 60.0
    assert fps.get_floor_plan(1) == fp1
    assert fps.get_floor_plan(2) == fp2
    assert fps.get_floor_plan(3) is None
    assert len(fps.plot_boundary) == 4
    assert len(fps.buildable_boundary) == 4
    assert fps.generation_metadata["algorithm"] == "ASAA_v2"


def test_floor_plan_set_all_valid_false_when_one_invalid():
    """Test FloorPlanSet all_valid returns False when any floor is invalid."""
    fp1 = FloorPlan(floor_number=1, is_valid=True)
    fp2 = FloorPlan(floor_number=2, is_valid=False)

    fps = FloorPlanSet(floor_plans=[fp1, fp2])
    assert fps.all_valid is False
