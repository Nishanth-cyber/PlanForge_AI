"""Verification tests asserting that all Phase-1 data models import cleanly."""


def test_import_id_utility():
    """Verify generate_id utility import."""
    from app.utils.ids import generate_id
    assert callable(generate_id)


def test_import_requirements():
    """Verify requirements model import."""
    from app.models.requirements import RoomRequirement, FloorRequirement, Requirements
    assert RoomRequirement is not None
    assert FloorRequirement is not None
    assert Requirements is not None


def test_import_planning():
    """Verify planning model import."""
    from app.models.planning import RoomSpec, FloorPlanSpec, PlanningSpec
    assert RoomSpec is not None
    assert FloorPlanSpec is not None
    assert PlanningSpec is not None


def test_import_allocation():
    """Verify allocation model import."""
    from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
    assert AllocatedRegion is not None
    assert Allocation is not None
    assert AllocationSet is not None


def test_import_doors_windows_staircase():
    """Verify door, window, and staircase intent model imports."""
    from app.models.doors import DoorIntent, DoorSpec
    from app.models.windows import WindowIntent, WindowSpec
    from app.models.staircase import StaircaseIntent, StaircaseSpec
    assert DoorIntent is not None
    assert DoorSpec is not None
    assert WindowIntent is not None
    assert WindowSpec is not None
    assert StaircaseIntent is not None
    assert StaircaseSpec is not None


def test_import_architectural_design():
    """Verify architectural design model import."""
    from app.models.architectural_design import (
        RoomDesign,
        RoomDesignProposal,
        ArchitecturalDesign,
        ArchitecturalDesignSet,
    )
    assert RoomDesign is not None
    assert RoomDesignProposal is not None
    assert ArchitecturalDesign is not None
    assert ArchitecturalDesignSet is not None


def test_import_geometry():
    """Verify geometry model import."""
    from app.models.geometry import (
        GeoWall,
        GeoDoor,
        GeoWindow,
        GeoStaircase,
        GeoRoom,
        Geometry,
        GeometrySet,
    )
    assert GeoWall is not None
    assert GeoDoor is not None
    assert GeoWindow is not None
    assert GeoStaircase is not None
    assert GeoRoom is not None
    assert Geometry is not None
    assert GeometrySet is not None


def test_import_floor_plan():
    """Verify floor plan model import."""
    from app.models.floor_plan import FloorPlan, FloorPlanSet
    assert FloorPlan is not None
    assert FloorPlanSet is not None


def test_import_validation():
    """Verify validation model import."""
    from app.models.validation import ValidationIssue, ValidationResult, ValidationReport
    assert ValidationIssue is not None
    assert ValidationResult is not None
    assert ValidationReport is not None


def test_import_events():
    """Verify event model import."""
    from app.models.events import Event, EventLog
    assert Event is not None
    assert EventLog is not None
