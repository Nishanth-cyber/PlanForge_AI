"""Unit tests verifying all structured geometry error conditions."""

import pytest
from app.geometry.engine import GeometryEngine
from app.geometry.exceptions import (
    CorridorConstructionError,
    DoorPlacementError,
    GeometryConstructionError,
    ImpossibleDimensionsError,
    InvalidRoomGeometryError,
    InvalidShapeParametersError,
    RoomOutOfBoundsError,
    StaircaseConstructionError,
    WindowPlacementError,
)
from app.geometry.geometry_utils import validate_polygon_coords
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)


def test_exception_inheritance():
    """Verify all specific exceptions inherit from GeometryConstructionError."""
    assert issubclass(InvalidRoomGeometryError, GeometryConstructionError)
    assert issubclass(RoomOutOfBoundsError, GeometryConstructionError)
    assert issubclass(ImpossibleDimensionsError, GeometryConstructionError)
    assert issubclass(InvalidShapeParametersError, GeometryConstructionError)
    assert issubclass(DoorPlacementError, GeometryConstructionError)
    assert issubclass(WindowPlacementError, GeometryConstructionError)
    assert issubclass(StaircaseConstructionError, GeometryConstructionError)
    assert issubclass(CorridorConstructionError, GeometryConstructionError)


def test_invalid_polygon_coords_error():
    """Verify InvalidRoomGeometryError on empty or fewer than 3 vertices."""
    with pytest.raises(InvalidRoomGeometryError):
        validate_polygon_coords([(0.0, 0.0), (1.0, 1.0)])


def test_missing_allocation_region_error():
    """Verify RoomOutOfBoundsError when room design references non-existent allocated region."""
    engine = GeometryEngine()

    design = ArchitecturalDesign(
        floor_number=1,
        rooms=[
            RoomDesign(
                room_type="study",
                allocated_region_id="non_existent_reg_123",
            )
        ],
    )
    alloc = Allocation(
        floor_number=1,
        allocated_regions=[],  # empty
    )

    with pytest.raises(RoomOutOfBoundsError):
        engine.construct_floor(design, alloc)


def test_missing_floor_allocation_error():
    """Verify GeometryConstructionError when an entire floor's allocation is missing."""
    engine = GeometryEngine()

    d_set = ArchitecturalDesignSet(
        designs=[ArchitecturalDesign(floor_number=2)]
    )
    a_set = AllocationSet(
        allocations=[Allocation(floor_number=1)]  # only floor 1
    )

    with pytest.raises(GeometryConstructionError):
        engine.construct(d_set, a_set)
